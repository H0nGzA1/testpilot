"""Celery app for test-run execution and GitLab issue sync.

Runs only when ``REDIS_URL`` is configured. Start the two processes alongside the API:

    celery -A app.celery_app.celery worker -l info --concurrency=$MAX_GLOBAL_CONCURRENCY
    celery -A app.celery_app.celery beat -l info

Run execution: the API calls ``fan_out_run`` which enqueues one ``run_case`` task per
case as a Celery ``chord``; the chord callback ``finalize_run`` aggregates the summary.
The worker's ``--concurrency`` IS the global browser budget — each case is one browser,
so N worker slots == at most N concurrent Chromiums across all runs/users (no in-process
semaphore needed; it is crash-safe and scales across machines by adding workers).

GitLab sync: the API enqueues ``push_issue`` on issue create/update/comment; beat runs
``poll_all_projects`` every ``gitlab_poll_interval_s`` seconds.
"""

from __future__ import annotations

import asyncio
import logging

from celery import Celery

from app.config import get_settings

log = logging.getLogger("testpilot.celery")
_settings = get_settings()

celery = Celery(
    "testpilot",
    broker=_settings.redis_url or None,
    backend=_settings.redis_url or None,
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    # One case == one browser == one pool slot, so prefetching four more per slot only
    # widens the blast radius: prefetched cases are acked already and die with the worker.
    worker_prefetch_multiplier=1,
    beat_schedule={
        "poll-gitlab": {
            "task": "app.celery_app.poll_all_projects",
            "schedule": float(_settings.gitlab_poll_interval_s),
        },
        "scan-suite-reminders": {
            "task": "app.celery_app.scan_suite_reminders",
            "schedule": 3600.0,  # hourly: email due/overdue suites (does not auto-run)
        },
        "reconcile-runs": {
            "task": "app.celery_app.reconcile_runs",
            "schedule": 60.0,  # a run whose worker died must not hang forever
        },
    },
)


@celery.task(name="app.celery_app.run_case")
def run_case(run_id: int, case_id: int) -> str:
    """Execute one test case (one browser). No Celery-level retry: execute_case already
    retries infra errors internally, and re-running here would launch a second browser."""
    from app.engine import execute_one_case

    return asyncio.run(execute_one_case(run_id, case_id))


@celery.task(name="app.celery_app.finalize_run")
def finalize_run(results: list, run_id: int) -> dict:
    """Chord callback: aggregate the run once every case task has returned."""
    from app.engine import finalize_run as _finalize

    return asyncio.run(_finalize(run_id))


def fan_out_run(run_id: int, case_ids: list[int]) -> None:
    """Fan a run's cases out as case-level tasks; a chord callback finalizes the run.
    Global concurrency is the worker's --concurrency (each case == one browser).

    ponytail: cases share one FIFO queue, so a large run's cases can occupy the whole
    budget ahead of a later small run (no per-run fairness). Add task priorities or a
    per-run queue only if starvation is actually observed.
    """
    from celery import chord, group

    header = group(run_case.s(run_id, cid) for cid in case_ids)
    chord(header)(finalize_run.s(run_id))


@celery.task(name="app.celery_app.reconcile_runs")
def reconcile_runs() -> list[int]:
    """Beat backstop: finish runs whose case tasks died with their worker. Without it a
    deploy in the middle of a run leaves that run at 'running' forever — the chord callback
    only fires when every case task returns, and a killed task never does."""
    from app.engine import reconcile_stale_runs

    return asyncio.run(reconcile_stale_runs())


@celery.task(
    name="app.celery_app.push_issue", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def push_issue(issue_id: int) -> None:
    from app.gitlab_sync import push_issue as _push

    asyncio.run(_push(issue_id))


def enqueue_push(issue_id: int) -> None:
    """Fire-and-forget push enqueue used by the API. No-ops when sync is disabled and
    never raises — issue create/update must not depend on Celery/GitLab being up."""
    if not _settings.redis_url:
        return
    try:
        push_issue.delay(issue_id)
    except Exception:
        log.warning("could not enqueue GitLab push for issue %s", issue_id, exc_info=True)


@celery.task(name="app.celery_app.scan_suite_reminders")
def scan_suite_reminders() -> int:
    """Hourly: email the runner (cc owner) for suites whose due_at has passed. Does NOT
    auto-run. Dedupes to one reminder per due window via the notification history."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app import notify
    from app.db import db_session
    from app.models import Notification, TestSuite

    async def _run() -> int:
        now = datetime.now(UTC)
        sent = 0
        async with db_session() as s:
            suites = (
                (
                    await s.execute(
                        select(TestSuite).where(
                            TestSuite.cadence != "none",
                            TestSuite.due_at.isnot(None),
                            TestSuite.due_at <= now,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for x in suites:
                targets = {x.runner_user_id, x.owner_user_id} - {None}
                if not targets:
                    continue
                already = (
                    await s.execute(
                        select(Notification.id)
                        .where(
                            Notification.suite_id == x.id,
                            Notification.type.in_(("reminder_due", "reminder_overdue")),
                            Notification.created_at >= x.due_at,
                        )
                        .limit(1)
                    )
                ).first()
                if already:  # already reminded for this due window
                    continue
                due = x.due_at if x.due_at.tzinfo else x.due_at.replace(tzinfo=UTC)
                overdue_days = (now - due).days
                typ = "reminder_overdue" if overdue_days >= 1 else "reminder_due"
                suffix = f"(已超期 {overdue_days} 天)" if overdue_days >= 1 else "(已到期)"
                for uid in targets:
                    await notify.push(
                        s,
                        user_id=uid,
                        type=typ,
                        title=f"待运行测试套件:{x.name}{suffix}",
                        body="请尽快运行该测试套件并复核结果。",
                        link=f"/projects/{x.project_id}/suites",
                        suite_id=x.id,
                    )
                    sent += 1
        return sent

    return asyncio.run(_run())


@celery.task(name="app.celery_app.poll_all_projects")
def poll_all_projects() -> int:
    from sqlalchemy import select

    from app.db import db_session
    from app.gitlab_sync import poll_project
    from app.models import Project

    async def _run() -> int:
        async with db_session() as s:
            ids = [
                p.id
                for p in (
                    await s.execute(select(Project).where(Project.gitlab_project.is_not(None)))
                )
                .scalars()
                .all()
            ]
        total = 0
        for pid in ids:
            try:
                total += await poll_project(pid)
            except Exception:
                log.exception("poll_project(%s) failed", pid)
        return total

    return asyncio.run(_run())

"""Engine loop: enqueue a run's cases, drain them with N concurrent workers, aggregate.

`drain` and `aggregate` are pure (stdlib only) so they are unit-testable without the DB
or browser stack. `run_suite` is the DB-backed wrapper.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, NamedTuple, TypeVar
from urllib.parse import urljoin

from app.config import get_settings

log = logging.getLogger("testpilot.engine")

# a run in one of these is over — no case of it should still be waiting to start
_TERMINAL = ("completed", "failed", "cancelled")

T = TypeVar("T")
R = TypeVar("R")


def resolve_start_url(case_start_url: str | None, base_url: str | None) -> str | None:
    """Where the browser opens. A case's start_url is normally a path like
    /visitor/master/park so the same case can run against dev/test/prod — join it onto the
    environment's base_url. Left bare it reached the browser as-is and Chromium read it as
    http://localhost/visitor/master/park → ERR_CONNECTION_REFUSED, then the agent wandered
    off to a search engine looking for the app."""
    if not case_start_url:
        return base_url
    if case_start_url.startswith(("http://", "https://")) or not base_url:
        return case_start_url
    return urljoin(base_url, case_start_url)


def _effective_prompt(c: Any) -> str:
    """The task the agent actually runs: the NL prompt, with preconditions prepended
    and test data appended when present. Structured `steps` stay documentation-only."""
    parts: list[str] = []
    if (c.preconditions or "").strip():
        parts.append(f"Preconditions: {c.preconditions.strip()}")
    parts.append(c.prompt)
    if (c.test_data or "").strip():
        parts.append(f"Test data: {c.test_data.strip()}")
    return "\n\n".join(parts)


async def drain(
    items: list[T],
    handler: Callable[[T], Awaitable[R]],
    concurrency: int,
    slot: asyncio.Semaphore | None = None,
) -> list[R]:
    """Run handler over every item with `concurrency` workers. Failure-isolated:
    a handler that raises yields an Exception in the results, never aborts the run.

    `slot`: a semaphore acquired around each handler call. Pass the SAME instance to
    concurrent drains to cap total in-flight work across all runs (the global budget).
    A worker blocks on the slot *before* running the handler, so per-item timeouts
    inside the handler never count queue-wait time."""
    queue: asyncio.Queue[T] = asyncio.Queue()
    for it in items:
        queue.put_nowait(it)
    results: list[R] = []
    lock = asyncio.Lock()

    async def run_one(item: T) -> Any:
        try:
            return await handler(item)
        except Exception as exc:
            return exc

    async def worker() -> None:
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if slot is not None:
                async with slot:
                    r: Any = await run_one(item)
            else:
                r = await run_one(item)
            async with lock:
                results.append(r)

    await asyncio.gather(*[worker() for _ in range(max(1, concurrency))])
    return results


_GLOBAL_SLOT: asyncio.Semaphore | None = None


def global_slot() -> asyncio.Semaphore:
    """Process-wide browser budget, created lazily inside the running loop. All runs
    share this one instance so simultaneous runs can't exceed max_global_concurrency."""
    global _GLOBAL_SLOT
    if _GLOBAL_SLOT is None:
        _GLOBAL_SLOT = asyncio.Semaphore(get_settings().max_global_concurrency)
    return _GLOBAL_SLOT


def _pct(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(q * len(ordered)))
    return ordered[idx]


def aggregate(statuses: list[str], latencies: list[int], flaky: int = 0) -> dict:
    total = len(statuses)
    passed = statuses.count("passed")
    return {
        "total": total,
        "passed": passed,
        "failed": statuses.count("failed"),
        "error": statuses.count("error"),
        "flaky": flaky,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "latency_p50_ms": int(median(latencies)) if latencies else 0,
        "latency_p95_ms": _pct(latencies, 0.95),
    }


def resolve_attempts(statuses: list[str]) -> tuple[str, bool]:
    """Given each attempt's status in order, return (final_status, flaky).
    flaky == passed only after one or more retries."""
    final = statuses[-1]
    return final, (final == "passed" and len(statuses) > 1)


class DefaultLogin(NamedTuple):
    """What a role-less case logs in with. `pw_cred_id` is the password account's row —
    needed to capture a session bundle from it once and cache it there, the same way a
    role account does."""

    login_state: str | None
    username: str | None
    password: str | None
    state_cred_id: int | None
    pw_cred_id: int | None


async def _resolve_login(session, run, env_id: int | None = None) -> DefaultLogin:
    """A run's default login (no case role): active storage_state credential (decrypted)
    > legacy project column; plus a robot password account for per-run prompt-login (apps
    that keep auth in sessionStorage). Filtered to the run's environment (or
    env-agnostic accounts). Secrets resolved here, never sent through the broker."""
    from sqlalchemy import or_, select

    from app.crypto import decrypt, secret_configured
    from app.models import Credential, Project

    project = await session.get(Project, run.project_id)
    login_state = project.login_state if project else None
    login_user: str | None = None
    login_pass: str | None = None
    state_cred_id: int | None = None
    pw_cred_id: int | None = None
    env_ok = or_(Credential.environment_id == env_id, Credential.environment_id.is_(None))
    if secret_configured():
        cred = (
            (
                await session.execute(
                    select(Credential).where(
                        Credential.project_id == run.project_id,
                        Credential.is_active == True,
                        Credential.type == "storage_state",
                        env_ok,
                    )
                )
            )
            .scalars()
            .first()
        )
        if cred is not None:
            login_state = decrypt(cred.secret)
            state_cred_id = cred.id
        pw_cred = (
            (
                await session.execute(
                    select(Credential)
                    .where(
                        Credential.project_id == run.project_id,
                        Credential.type == "password",
                        env_ok,
                    )
                    .order_by(Credential.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if pw_cred is not None:
            login_user = pw_cred.username
            login_pass = decrypt(pw_cred.secret)
            pw_cred_id = pw_cred.id
    return DefaultLogin(login_state, login_user, login_pass, state_cred_id, pw_cred_id)


async def prepare_run(run_id: int) -> list[int] | None:
    """Validate the run and record total_count; return its case ids (order preserved).
    Does NOT mark the run running — the first case to start flips pending->running so a
    queued run shows as queued, not a silent 0/N. Returns None if the run isn't runnable."""
    from app.db import db_session
    from app.models import Run

    async with db_session() as s:
        run = await s.get(Run, run_id)
        if run is None or run.status not in ("pending", "running"):
            return None
        case_ids = list(run.case_ids or [])
        run.total_count = len(case_ids)
        await s.commit()
        return case_ids


async def _role_candidates(
    session, project_id: int, role: str, env_id: int | None = None
) -> list[dict]:
    """Decrypted accounts for a role in a project + environment (env-null = any env)."""
    from sqlalchemy import or_, select

    from app.crypto import decrypt, secret_configured
    from app.models import Credential

    if not secret_configured():
        return []
    rows = (
        (
            await session.execute(
                select(Credential)
                .where(
                    Credential.project_id == project_id,
                    Credential.role == role,
                    or_(Credential.environment_id == env_id, Credential.environment_id.is_(None)),
                )
                .order_by(Credential.id)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": c.id,
            "type": c.type,
            "username": c.username,
            "secret": decrypt(c.secret),
            "label": c.label,
        }
        for c in rows
    ]


# A capture is only worth re-using while the app-side session behind it is still alive.
# Most systems expire a session around 30 minutes, so SESSION_TTL_MIN defaults just under
# that; the old 8h guess meant a bundle stayed "fresh" for hours after the server had
# forgotten it, and every case restored a corpse and landed on the login page.
def bundle_ttl() -> timedelta:
    return timedelta(minutes=get_settings().session_ttl_min)


# A herd of self-heals must not become a herd of logins. The rate limit on the app under
# test is per-account, so what matters is how often we log in, not how many browsers run.
RECAPTURE_COOLDOWN_S = 90


def bundle_is_fresh(
    expires_at: datetime | None,
    now: datetime | None = None,
    min_remaining_s: int = 0,
) -> bool:
    """Is the stored bundle usable for the next `min_remaining_s` seconds?

    Callers pass the case's timeout, so a case never starts on a session due to die
    mid-run. No expiry recorded means it was captured before expiry was tracked — so it is
    at least as old as that change and stale by definition. Trusting that (the first cut
    did) kept the exact bug it was meant to fix: run 44 served a day-old dead session to
    16 browsers at once and every one fell through to the login form."""
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:  # sqlite drops the offset on round-trip; postgres keeps it
        expires_at = expires_at.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) + timedelta(seconds=min_remaining_s) < expires_at


def captured_recently(
    expires_at: datetime | None,
    ttl: timedelta,
    within_s: int,
    now: datetime | None = None,
) -> bool:
    """Was this bundle captured in the last `within_s` seconds? capture time is implied by
    the expiry (captured_at == expires_at - ttl). Used to collapse a burst of forced
    re-captures — every case of a run noticing the same dead session — into one login."""
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return (expires_at - ttl) > (now or datetime.now(UTC)) - timedelta(seconds=within_s)


async def _ensure_bundle(
    cred_id: int,
    field: str,
    base_url: str | None,
    username: str | None,
    password: str,
    timeout_s: int,
    force: bool = False,
) -> str | None:
    """Reusable session for an account, stored in credential.<field> (encrypted). Returns
    its captured bundle, capturing one (single-flight) when missing — or force-recapturing
    on `force=True` (P3 self-heal after a dead session). Only ONE worker captures per
    credential (leasing.capture_lock); the rest wait for the bundle to land in the DB.
    Returns None if capture isn't possible (caller falls back to prompt-login)."""
    import asyncio as _asyncio
    import time as _time

    from app import leasing
    from app.crypto import decrypt, encrypt
    from app.db import db_session
    from app.executor import capture_session
    from app.models import Credential

    ttl = bundle_ttl()

    async def _read() -> str | None:
        """The stored bundle, but only if it will outlive the case about to use it."""
        async with db_session() as s:
            c = await s.get(Credential, cred_id)
            v = getattr(c, field, None) if c else None
            if not v or not bundle_is_fresh(c.expires_at, min_remaining_s=timeout_s):
                return None
            return decrypt(v)

    async def _read_if_just_captured() -> str | None:
        """Someone re-captured while we queued for the lock — take theirs, don't log in
        again. This is what keeps N cases self-healing off the same dead session from
        becoming N logins against a per-account rate limit."""
        async with db_session() as s:
            c = await s.get(Credential, cred_id)
            v = getattr(c, field, None) if c else None
            if not v or not captured_recently(c.expires_at, ttl, RECAPTURE_COOLDOWN_S):
                return None
            return decrypt(v)

    if not force:
        existing = await _read()
        if existing:
            return existing
    elif (just := await _read_if_just_captured()) is not None:
        return just
    if not base_url or not username:
        return None
    got = await leasing.capture_lock(cred_id, ttl_s=timeout_s + 60)
    try:
        if not got:
            # another worker is (re)capturing — wait for a bundle to land
            end = _time.monotonic() + timeout_s
            while _time.monotonic() < end:
                await _asyncio.sleep(2.0)
                b = await _read()
                if b:
                    return b
            return None
        # double-check under the lock: someone may have captured while we queued
        b = await (_read() if not force else _read_if_just_captured())
        if b:
            return b
        try:
            bundle = await capture_session(base_url, username, password)
        except Exception:
            return None
        async with db_session() as s:
            c = await s.get(Credential, cred_id)
            if c is not None:
                setattr(c, field, encrypt(bundle))
                c.expires_at = datetime.now(UTC) + ttl
        return bundle
    finally:
        if got:
            await leasing.capture_unlock(cred_id)


async def _update_account_health(account_id: int, status: str, error_msg: str | None) -> None:
    """Passive health: mark the leased account healthy (pass) or unhealthy (error). On the
    first transition to unhealthy, notify the account's creator."""
    from datetime import datetime

    from sqlalchemy import select

    from app import notify
    from app.db import db_session
    from app.models import Credential, User

    async with db_session() as s:
        cred = await s.get(Credential, account_id)
        if cred is None:
            return
        cred.last_checked_at = datetime.now(UTC)
        if status == "passed":
            cred.healthy = True
            cred.last_error = None
            return
        was_healthy = cred.healthy
        cred.healthy = False
        cred.last_error = (error_msg or "登录/执行失败")[:500]
        if was_healthy and cred.created_by:
            u = (
                (await s.execute(select(User).where(User.email == cred.created_by)))
                .scalars()
                .first()
            )
            if u is not None:
                await notify.push(
                    s,
                    user_id=u.id,
                    type="account_unhealthy",
                    title=f"账号异常:{cred.label or cred.username or '#' + str(cred.id)}",
                    body=f"角色「{cred.role or '默认'}」的账号执行失败:{cred.last_error}",
                    link=f"/projects/{cred.project_id}/settings",
                )


async def _finalize_case_error(live_id: int, run_id: int, msg: str) -> str:
    """Mark a live result as error (e.g. no account for the role) and bump progress."""
    from app.db import db_session
    from app.models import Run, RunResult

    async with db_session() as s:
        row = await s.get(RunResult, live_id)
        if row is not None:
            row.status = "error"
            row.error = msg[:500]
            row.attempts = 1
        run_row = await s.get(Run, run_id)
        if run_row is not None:
            run_row.processed_count += 1
    return "error"


async def execute_one_case(run_id: int, case_id: int) -> str:
    """Run one case end-to-end: resolve the account (by the case's role, leasing a free
    one), drive the browser agent with infra-error retries, persist the RunResult, bump
    progress, and flip the run pending->running on first start. Never raises — returns the
    final status, so it is a safe Celery task body and the chord always reaches finalize."""
    from datetime import datetime

    from app import leasing
    from app.db import db_session
    from app.executor import CaseSpec, execute_case
    from app.models import Project, Run, RunResult, TestCase

    lease_id: int | None = None
    run_slot: int | None = None
    try:
        # Wait for one of the run's concurrency slots before doing ANY work. fan_out_run
        # hands every case to Celery at once, so until now the only cap was the worker's
        # --concurrency (16) and the project's 并发数 did nothing: a 49-case run opened 16
        # browsers in the same instant, which is what turned one dead session into a login
        # storm. Re-reads the run each round so cancelling releases the waiters too.
        while run_slot is None:
            async with db_session() as s:
                run = await s.get(Run, run_id)
                # Any terminal state, not just cancelled: the reconciler marks an abandoned
                # run 'completed', and a waiter that only checks for 'cancelled' would spin
                # on a run nobody will ever finish until the worker is restarted.
                if run is None or run.status in _TERMINAL:
                    return "error"
                slots = max(1, run.concurrency or 1)
                project = await s.get(Project, run.project_id)
                # The lease has to outlive the case holding it, or it expires mid-browser,
                # the slot frees, and another case starts on top of it — 并发 drifts past
                # its cap silently. Sized off the PROJECT's timeout: VRS overrides it to
                # 1200s against a global default of 150s, which would have expired the
                # lease at 600s with the browser still running.
                slot_ttl = int(
                    hold_limit(
                        (project.case_timeout_s if project else None)
                        or get_settings().case_timeout_s
                    ).total_seconds()
                )
            run_slot = await leasing.run_slot_acquire(run_id, slots, ttl_s=slot_ttl, wait_s=20)

        role: str | None = None
        candidates: list[dict] = []
        default_login = DefaultLogin(None, None, None, None, None)
        # setup: load run/case/project, plan login (role candidates or default), flip
        # pending->running (idempotent), create the live row.
        async with db_session() as s:
            run = await s.get(Run, run_id)
            if run is None or run.status in _TERMINAL:  # finished while we queued for a slot
                return "error"
            case = await s.get(TestCase, case_id)
            if case is None:
                return "error"
            project = await s.get(Project, run.project_id)
            env_id = run.environment_id
            role = (case.role or "").strip() or None
            if role:
                candidates = await _role_candidates(s, run.project_id, role, env_id)
            else:
                default_login = await _resolve_login(s, run, env_id)
            _s = get_settings()
            to_s = (project.case_timeout_s if project else None) or _s.case_timeout_s
            max_st = (project.case_max_steps if project else None) or _s.case_max_steps
            # base_url from the run's environment, falling back to the project's
            base_url = project.base_url if project else None
            if env_id is not None:
                from app.models import Environment

                env = await s.get(Environment, env_id)
                if env is not None and env.base_url:
                    base_url = env.base_url
            prompt = _effective_prompt(case)
            expected = case.expected
            start_url = resolve_start_url(case.start_url, base_url)
            if run.status == "pending":
                run.status = "running"
                run.started_at = datetime.now(UTC)
            live = RunResult(run_id=run_id, case_id=case_id, status="running", diagnostics=[])
            s.add(live)
            await s.flush()
            live_id = live.id

        # role set but no account for it -> explicit failure (never silently use a wrong one)
        if role and not candidates:
            return await _finalize_case_error(live_id, run_id, f"角色「{role}」没有可用账号")

        login_state: str | None = None
        login_user: str | None = None
        login_pass: str | None = None
        account_label: str | None = None
        # P3 self-heal source: which credential's bundle to re-capture (and how) if the
        # restored session turns out dead. None => nothing to heal (e.g. prompt-login).
        bundle_cred_id: int | None = None
        bundle_field: str = "session_bundle"
        refresh_user: str | None = None
        refresh_pass: str | None = None
        if role:
            # lease a free account for this role; wait up to the case timeout, else fail
            lease_id = await leasing.acquire(
                [c["id"] for c in candidates], ttl_s=to_s + 30, wait_s=to_s
            )
            if lease_id is None:
                return await _finalize_case_error(live_id, run_id, f"角色「{role}」的账号都在忙")
            acct = next(c for c in candidates if c["id"] == lease_id)
            if acct["type"] == "storage_state":
                login_state = acct["secret"]
            else:
                # password role account: reuse a captured bundle (capture once, single-flight)
                # so we don't prompt-login every case; fall back to prompt-login if none.
                bundle = await _ensure_bundle(
                    acct["id"], "session_bundle", base_url, acct["username"], acct["secret"], to_s
                )
                if bundle:
                    login_state = bundle
                    bundle_cred_id = acct["id"]
                    bundle_field = "session_bundle"
                    refresh_user = acct["username"]
                    refresh_pass = acct["secret"]
                else:
                    login_user = acct["username"]
                    login_pass = acct["secret"]
            who = acct["label"] or acct["username"] or f"#{acct['id']}"
            account_label = f"{role} · {who}"
        else:
            login_state, login_user, login_pass, state_cred_id, pw_cred_id = default_login
            # default account's bundle lives in the storage_state cred's `secret`; the robot
            # password account (login_user/pass) is how we re-capture it on a dead session.
            if login_state and state_cred_id and login_user:
                bundle_cred_id = state_cred_id
                bundle_field = "secret"
                refresh_user = login_user
                refresh_pass = login_pass
            elif login_user and login_pass and pw_cred_id:
                # No captured session yet. Capture one from the default password account and
                # cache it on that row — exactly what a role account already does. Without
                # this a role-less case typed the login form on EVERY case of EVERY run,
                # burning steps before it could even reach the module under test.
                bundle = await _ensure_bundle(
                    pw_cred_id, "session_bundle", base_url, login_user, login_pass, to_s
                )
                if bundle:
                    login_state = bundle
                    bundle_cred_id = pw_cred_id
                    bundle_field = "session_bundle"
                    refresh_user = login_user
                    refresh_pass = login_pass

        spec = CaseSpec(
            case_id=case_id,
            prompt=prompt,
            expected=expected,
            start_url=start_url,
            login_state=login_state,
            login_username=login_user,
            login_password=login_pass,
            timeout_s=to_s,
            max_steps=max_st,
            result_id=live_id,
        )

        async def on_step(steps: list) -> None:
            async with db_session() as s:
                row = await s.get(RunResult, live_id)
                if row is not None:
                    row.diagnostics = steps

        async def should_abort() -> bool:
            """Cancelling a run used to only flip the run row: cases already driving a
            browser ran to completion, so the button did nothing for up to case_timeout_s
            each and the results sat at 'running' forever. Checked once per step, on the
            session the step callback opens anyway."""
            async with db_session() as s:
                r = await s.get(Run, run_id)
                return r is None or r.status == "cancelled"

        from dataclasses import replace

        retries = get_settings().case_retries
        attempt_statuses: list[str] = []
        r = None
        healed = False
        infra_attempts = 0
        while True:
            r = await execute_case(spec, on_step=on_step, should_abort=should_abort)
            attempt_statuses.append(r.status)
            # A timeout means the case wants more wall clock than its budget. Neither
            # re-attempt below can change that, and each one burns another full budget
            # (10 minutes at case_timeout_s=600). It also stops the self-heal from
            # misreading a run cut off mid-flight as a dead session: the last URL of a
            # timed-out attempt says nothing about whether the login still works.
            if r.timed_out:
                break
            # P3: dead restored session (ended on a login page) → invalidate + re-capture +
            # retry once. This one-shot heal is separate from the infra-error retries.
            if (
                r.auth_failed
                and not healed
                and bundle_cred_id is not None
                and refresh_user
                and base_url
            ):
                healed = True
                fresh = await _ensure_bundle(
                    bundle_cred_id,
                    bundle_field,
                    base_url,
                    refresh_user,
                    refresh_pass,
                    to_s,
                    force=True,
                )
                if fresh:
                    spec = replace(spec, login_state=fresh)
                    continue
            if r.status != "error":  # only infra errors are retried, not judge failures
                break
            infra_attempts += 1
            if infra_attempts > retries:
                break
        final, flaky = resolve_attempts(attempt_statuses)

        async with db_session() as s:
            row = await s.get(RunResult, live_id)
            if row is not None:
                row.status = final
                row.attempts = len(attempt_statuses)
                row.flaky = flaky
                row.video_url = r.video_url
                row.trace_url = r.trace_url
                row.steps = r.steps
                # final history-based diagnostics (with results/errors) supersede live ones
                row.diagnostics = r.diagnostics or row.diagnostics
                row.judge_reason = r.judge_reason
                row.final_answer = r.final_answer
                row.account_label = account_label
                row.latency_ms = r.latency_ms
                row.error = r.error
            run_row = await s.get(Run, run_id)
            if run_row is not None:
                run_row.processed_count += 1
                if final == "passed":
                    run_row.passed_count += 1
        # passive account health: the leased role account is healthy on a pass, unhealthy
        # on an infra error (likely login). A judge 'failed' is a test bug, not the account.
        if lease_id is not None and final in ("passed", "error"):
            await _update_account_health(lease_id, final, r.error if r else None)
        return final
    except Exception:
        # never propagate: a raising case task would break the Celery chord so finalize
        # would never fire. The run's counters/summary are reconciled in finalize_run.
        return "error"
    finally:
        await leasing.release(lease_id)
        await leasing.run_slot_release(run_slot)


async def finalize_run(run_id: int) -> dict:
    """Aggregate the persisted results into the run summary and mark it completed.
    Idempotent: safe as a Celery chord callback and as the in-process tail."""
    from datetime import datetime

    from sqlalchemy import select

    from app.db import db_session
    from app.models import Run, RunResult

    async with db_session() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return {"error": f"run {run_id} missing"}
        res_rows = (
            (await session.execute(select(RunResult).where(RunResult.run_id == run_id)))
            .scalars()
            .all()
        )
        summary = aggregate(
            [x.status for x in res_rows],
            [x.latency_ms for x in res_rows],
            flaky=sum(1 for x in res_rows if x.flaky),
        )
        run.summary = summary
        run.processed_count = len(res_rows)
        run.passed_count = summary["passed"]
        run.status = "completed" if run.status != "cancelled" else "cancelled"
        run.finished_at = datetime.now(UTC)
        if run.suite_id is not None:
            await _finalize_suite(session, run, summary)
        await session.commit()

    # Proactive Feishu push to the project's bound chat (best-effort, outside the txn).
    try:
        from app import feishu_notify

        await feishu_notify.push_run_result(run_id)
    except Exception:
        pass
    return summary


def hold_limit(timeout_s: int) -> timedelta:
    """The longest a single case can legitimately hold a slot, or go silent.

    It can spend one timeout waiting for a free account for its role, one capturing a
    session bundle, and one actually running — plus judge and upload slack. Both the
    run-concurrency lease and the stale-run reconciler are sized off this: a lease shorter
    than it frees a slot with a browser still on it (并发 drifts past its cap), and a
    reconciler shorter than it kills a healthy run."""
    return timedelta(seconds=timeout_s * 3 + 300)


def stall_limit(timeout_s: int, cancelled: bool = False) -> timedelta:
    """How long a run may go completely silent before we conclude nothing is running it.
    A live case rewrites its result row after every browser step, so silence is the signal.
    A cancelled run gets a much shorter fuse: its cases stop at their next step."""
    return timedelta(seconds=timeout_s + 60) if cancelled else hold_limit(timeout_s)


def _aware(dt: datetime | None) -> datetime | None:
    """sqlite drops the offset on round-trip; postgres keeps it."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def reconcile_stale_runs(now: datetime | None = None) -> list[int]:
    """Finish runs whose case tasks died with their worker. Returns the ids finalized.

    Celery acks a case task when it hands it to a worker, so a worker restart — a deploy,
    an OOM kill — drops every case that worker held, with no redelivery. Those RunResult
    rows stay 'running' forever, processed_count freezes, and the chord callback that
    finalizes the run never fires. Nothing in the system could then move that run: run 44
    sat at 43/49 with six cases 'running' and no finished_at for three days after a deploy
    recreated the worker mid-run.

    Beat calls this every minute. A run silent for longer than one case can legitimately
    take has no workers left, so terminalize its unfinished cases and finalize it."""
    from sqlalchemy import select

    from app.db import db_session
    from app.models import Project, Run, RunResult, TestCase

    now = now or datetime.now(UTC)
    dead: list[int] = []
    async with db_session() as s:
        runs = (
            (
                await s.execute(
                    select(Run).where(
                        Run.finished_at.is_(None),
                        Run.status.in_(("pending", "running", "cancelled")),
                    )
                )
            )
            .scalars()
            .all()
        )
        for run in runs:
            project = await s.get(Project, run.project_id)
            timeout_s = (
                project.case_timeout_s if project else None
            ) or get_settings().case_timeout_s
            beats = [_aware(r.updated_at) for r in await _run_rows(s, run.id)]
            beats += [_aware(run.started_at), _aware(run.created_at)]
            if now - max(b for b in beats if b is not None) >= stall_limit(
                timeout_s, run.status == "cancelled"
            ):
                dead.append(run.id)

    finalized: list[int] = []
    for rid in dead:
        # One transaction per run: a run that cannot be written must not take the rest of
        # the backlog down with it. The first live pass hit exactly that — an old run
        # referencing a since-deleted case raised a foreign-key error that rolled back
        # every other run in the same session, so nothing got reconciled at all.
        try:
            async with db_session() as s:
                run = await s.get(Run, rid)
                why = (
                    "运行已取消"
                    if run.status == "cancelled"
                    else "执行进程中断(worker 重启或被回收)"
                )
                rows = await _run_rows(s, rid)
                for r in rows:
                    if r.status == "running":
                        r.status = "error"
                        r.error = why
                # A case whose task died before it could open a row would otherwise vanish
                # from the report — record it so the run's total and its table agree, and
                # so "只重跑失败用例" can pick it up. Cases deleted since the run started
                # get no row: there is nothing left to re-run and the FK would reject it.
                missing = [c for c in (run.case_ids or []) if c not in {r.case_id for r in rows}]
                still_exist = (
                    (await s.execute(select(TestCase.id).where(TestCase.id.in_(missing))))
                    .scalars()
                    .all()
                )
                for cid in still_exist:
                    s.add(
                        RunResult(
                            run_id=rid,
                            case_id=cid,
                            status="error",
                            error=f"未执行:{why}",
                            diagnostics=[],
                        )
                    )
            await finalize_run(rid)
            finalized.append(rid)
        except Exception:
            log.exception("could not finish stale run %s", rid)
    return finalized


async def _run_rows(session, run_id: int) -> list:
    from sqlalchemy import select

    from app.models import RunResult

    return list(
        (await session.execute(select(RunResult).where(RunResult.run_id == run_id))).scalars().all()
    )


# cadence -> next-due delta (kept here so engine doesn't import api; mirrors api._CADENCE)
_CADENCE_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14, "monthly": 30}


async def _finalize_suite(session, run, summary: dict) -> None:
    """A suite run finished: update the suite's last_* + advance its due date, then
    notify the owner and the actual runner (failures always emailed)."""
    from datetime import datetime, timedelta

    from app import notify
    from app.models import TestSuite

    suite = await session.get(TestSuite, run.suite_id)
    if suite is None:
        return
    suite.last_run_id = run.id
    suite.last_status = run.status
    suite.last_run_at = run.finished_at
    days = _CADENCE_DAYS.get(suite.cadence)
    if days is not None:
        suite.due_at = (run.finished_at or datetime.now(UTC)) + timedelta(days=days)

    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0) + summary.get("error", 0)
    title = f"套件运行完成:{suite.name}(通过 {passed}/{total})"
    body = f"通过率 {round(100 * passed / total) if total else 0}%,失败/异常 {failed} 条。"
    recipients = {suite.owner_user_id, run.ran_by_user_id} - {None}
    link = f"/projects/{suite.project_id}/runs/{run.id}"
    for uid in recipients:
        await notify.push(
            session,
            user_id=uid,
            type="run_done",
            title=title,
            body=body,
            link=link,
            suite_id=suite.id,
            run_id=run.id,
        )


async def run_suite(run_id: int) -> dict:
    """In-process fallback (no Redis/Celery): prepare, drain every case under the global
    slot at the run's per-run concurrency, then finalize. The Celery path fans the same
    cases out as case-level tasks instead — see app.celery_app.fan_out_run."""
    from app.db import db_session
    from app.models import Run

    case_ids = await prepare_run(run_id)
    if case_ids is None:
        return {"error": f"run {run_id} not runnable"}
    async with db_session() as s:
        run = await s.get(Run, run_id)
        concurrency = (run.concurrency if run else None) or 2
    await drain(
        case_ids,
        lambda cid: execute_one_case(run_id, cid),
        concurrency,
        slot=global_slot(),
    )
    return await finalize_run(run_id)

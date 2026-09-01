"""Runnable check: re-running a run's failures skips the cases that already passed.

A 49-case VRS run is about two hours. After fixing something you want the verdict on the
19 that failed, not another two hours re-proving the 18 that passed.

python -m pytest tests/test_rerun_failed_only.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")


def _run(tmp_db: str) -> dict:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = "x" * 32
    os.environ.pop("AUTH_ENABLED", None)

    import app.api as api
    import app.db as db
    from app.config import get_settings
    from app.main import create_app
    from app.models import Project, Run, RunResult, TestCase
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()
    db._engine = db._Session = None

    async def main() -> dict:
        await db.init_db()
        api._launch = lambda run_id: asyncio.sleep(0)  # never drive a real browser
        out: dict = {}
        async with db.db_session() as s:
            p = Project(name="VRS", run_concurrency=6)
            s.add(p)
            await s.flush()
            cases = [TestCase(project_id=p.id, name=f"c{i}", prompt="x") for i in range(4)]
            for c in cases:
                s.add(c)
            await s.flush()
            ids = [c.id for c in cases]
            run = Run(
                project_id=p.id,
                name="re-run of run 2026/8/28 16:01:57",  # already a re-run: prefixes must not nest
                case_ids=ids,
                status="completed",
                total_count=4,
                concurrency=2,  # created before 并发数 was raised
            )
            s.add(run)
            await s.flush()
            # passed / failed / error, and one case with no row at all (its worker died)
            for cid, status in zip(ids[:3], ["passed", "failed", "error"], strict=True):
                s.add(RunResult(run_id=run.id, case_id=cid, status=status))
            out["ids"], out["run_id"] = ids, run.id

        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post(f"/api/runs/{out['run_id']}/rerun?only=failing")
            assert r.status_code < 400, r.text
            out["failed_rerun"] = r.json()

            r = await ac.post(f"/api/runs/{out['run_id']}/rerun?only=error")
            assert r.status_code < 400, r.text
            out["error_rerun"] = r.json()

            # an SPA cached from before `only` existed still sends the old parameter; it
            # must keep meaning "failing", not silently fall back to a full two-hour run
            r = await ac.post(f"/api/runs/{out['run_id']}/rerun?failed_only=true")
            assert r.status_code < 400, r.text
            out["legacy_rerun"] = r.json()

            out["bogus_status"] = (
                await ac.post(f"/api/runs/{out['run_id']}/rerun?only=nonsense")
            ).status_code

            r = await ac.post(f"/api/runs/{out['run_id']}/rerun")
            assert r.status_code < 400, r.text
            out["full_rerun"] = r.json()

            # a run where everything passed has nothing to re-run — say so, don't start
            # an empty run that instantly "completes" with a 0/0 report
            async with db.db_session() as s:
                clean = Run(project_id=1, name="all green", case_ids=[ids[0]], total_count=1)
                s.add(clean)
                await s.flush()
                s.add(RunResult(run_id=clean.id, case_id=ids[0], status="passed"))
                clean_id = clean.id
            out["clean_status"] = (
                await ac.post(f"/api/runs/{clean_id}/rerun?only=failing")
            ).status_code
            out["clean_error_status"] = (
                await ac.post(f"/api/runs/{clean_id}/rerun?only=error")
            ).status_code
        return out

    return asyncio.run(main())


def test_rerun_failed_only_keeps_everything_that_did_not_pass(tmp_path) -> None:
    o = _run(str(tmp_path / "tp.db"))
    passed, failed, errored, never_ran = o["ids"]

    assert o["failed_rerun"]["case_ids"] == [failed, errored, never_ran], (
        "a re-run of failures takes the judge failures, the infra errors AND the cases "
        "that never produced a result — only a real pass is skipped"
    )
    assert passed not in o["failed_rerun"]["case_ids"]
    assert o["failed_rerun"]["total_count"] == 3

    # the full re-run is unchanged
    assert o["full_rerun"]["case_ids"] == o["ids"]

    # names stay readable instead of growing a stack of "re-run of re-run of …"
    assert o["failed_rerun"]["name"] == "re-run of failures in run 2026/8/28 16:01:57"
    assert o["full_rerun"]["name"] == "re-run of run 2026/8/28 16:01:57"

    assert o["clean_status"] == 400, "nothing to re-run must be an error, not an empty run"
    assert o["clean_error_status"] == 400
    assert o["bogus_status"] == 400, "an unknown set must be refused, not treated as 'all'"

    assert o["legacy_rerun"]["case_ids"] == o["failed_rerun"]["case_ids"], (
        "the pre-`only` parameter must keep its meaning for a cached SPA"
    )


def test_rerun_errors_only_leaves_judge_failures_alone(tmp_path) -> None:
    """A judge 'failed' is a finding about the product — re-running it proves nothing. An
    'error' is a timeout or a dead session: the tool never got a verdict, so it is the one
    worth another attempt. VRS run 45: 17 failed, 7 error, all seven of them timeouts."""
    o = _run(str(tmp_path / "tp.db"))
    passed, failed, errored, never_ran = o["ids"]

    assert o["error_rerun"]["case_ids"] == [errored, never_ran], (
        "only the infra outcomes — plus a case that never produced a result at all, which "
        "is an infra outcome too"
    )
    assert failed not in o["error_rerun"]["case_ids"]
    assert passed not in o["error_rerun"]["case_ids"]
    assert o["error_rerun"]["name"] == "re-run of errors in run 2026/8/28 16:01:57"

    # raising 并发数 in project settings has to reach re-runs, which is exactly when you
    # are trying to make a two-hour run shorter
    assert o["failed_rerun"]["concurrency"] == 6


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        import pathlib

        test_rerun_failed_only_keeps_everything_that_did_not_pass(pathlib.Path(d))
    print("ok")

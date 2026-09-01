"""Runnable check: cancelling a run reaches cases that are already driving a browser.

Cancel only flipped the run row, and a case checked that row once — at startup. Anything
already running kept going for up to case_timeout_s, so the button appeared to do nothing
and the results sat at 'running' forever. VRS run 42 was cancelled with 13 cases still
hammering the app under test's login rate limiter.

python -m pytest tests/test_cancel_stops_inflight.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")


def _run(tmp_db: str, cancel_after_step: int | None) -> dict:
    """Run one case whose stubbed executor emits steps, cancelling the run partway."""
    from cryptography.fernet import Fernet

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = Fernet.generate_key().decode()
    os.environ.pop("AUTH_ENABLED", None)

    import app.db as db
    import app.engine as engine
    import app.executor as executor
    from app.config import get_settings
    from app.models import Environment, Project, Run, TestCase

    get_settings.cache_clear()
    db._engine = db._Session = None

    steps_taken: list[int] = []

    async def fake_execute_case(spec, on_step=None, should_abort=None):  # noqa: ANN001
        """Stand in for the browser agent: 10 steps, stopping early if asked to."""
        for i in range(1, 11):
            steps_taken.append(i)
            if on_step is not None:
                await on_step([{"i": i, "action": "click", "screenshot": None}])
            if cancel_after_step is not None and i == cancel_after_step:
                async with db.db_session() as s:
                    r = await s.get(Run, run_holder["id"])
                    r.status = "cancelled"  # what POST /runs/{id}/cancel does
            if should_abort is not None and await should_abort():
                return executor.ResultSpec(case_id=spec.case_id, status="error", error="cancelled")
        return executor.ResultSpec(case_id=spec.case_id, status="passed")

    run_holder: dict = {}

    async def main() -> dict:
        await db.init_db()
        executor.execute_case = fake_execute_case

        async with db.db_session() as s:
            p = Project(name="VRS")
            s.add(p)
            await s.flush()
            s.add(Environment(project_id=p.id, name="test", base_url="http://x", is_default=True))
            case = TestCase(project_id=p.id, name="c1", prompt="do it")
            s.add(case)
            await s.flush()
            run = Run(project_id=p.id, name="r", case_ids=[case.id], total_count=1)
            s.add(run)
            await s.flush()
            run_holder["id"] = run.id
            case_id = case.id

        final = await engine.execute_one_case(run_holder["id"], case_id)
        return {"final": final, "steps": len(steps_taken)}

    return asyncio.run(main())


def test_cancelling_stops_a_case_that_is_already_running(tmp_path) -> None:
    o = _run(str(tmp_path / "cancel.db"), cancel_after_step=3)

    assert o["steps"] == 3, (
        f"the case ran {o['steps']} steps after being cancelled at step 3 — cancel must "
        "reach a case that is already driving a browser, not just flip the run row"
    )
    assert o["final"] == "error", "an aborted case finalises instead of sitting at 'running'"


def test_an_uncancelled_case_runs_to_the_end(tmp_path) -> None:
    o = _run(str(tmp_path / "normal.db"), cancel_after_step=None)
    assert o["steps"] == 10
    assert o["final"] == "passed"

"""Runnable check: a run never opens more browsers than its concurrency setting.

fan_out_run hands every case to Celery at once, so the only cap was the worker's
--concurrency (16 on the test host) and the project's 并发数 did nothing. Run 44 started
16 browsers in the same instant; 7 of them hit the login page together and the burst
tripped the app under test's rate limiter.

python -m pytest tests/test_run_concurrency.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")

CASES = 8
CONCURRENCY = 2


def _run(tmp_db: str, cancel_mid_wait: bool = False) -> dict:
    """Run CASES cases through execute_one_case at once and record how many stubbed
    browsers were ever alive at the same moment."""
    from cryptography.fernet import Fernet

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = Fernet.generate_key().decode()
    os.environ.pop("AUTH_ENABLED", None)
    os.environ.pop("REDIS_URL", None)  # in-process leasing path

    import app.db as db
    import app.engine as engine
    import app.executor as executor
    import app.leasing as leasing
    from app.config import get_settings
    from app.models import Environment, Project, Run, TestCase

    get_settings.cache_clear()
    db._engine = db._Session = None
    leasing._LOCAL_LEASED.clear()

    live = 0
    peak = 0

    async def fake_execute_case(spec, on_step=None, should_abort=None):  # noqa: ANN001
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.05)  # hold the "browser" open long enough to overlap
        live -= 1
        return executor.ResultSpec(case_id=spec.case_id, status="passed")

    async def main() -> dict:
        await db.init_db()
        executor.execute_case = fake_execute_case

        async with db.db_session() as s:
            p = Project(name="VRS")
            s.add(p)
            await s.flush()
            s.add(Environment(project_id=p.id, name="test", base_url="http://x", is_default=True))
            ids = []
            for i in range(CASES):
                c = TestCase(project_id=p.id, name=f"c{i}", prompt="do it")
                s.add(c)
                await s.flush()
                ids.append(c.id)
            run = Run(
                project_id=p.id,
                name="r",
                case_ids=ids,
                total_count=CASES,
                concurrency=CONCURRENCY,
            )
            s.add(run)
            await s.flush()
            run_id = run.id

        # every case dispatched at once, exactly what Celery does
        await asyncio.gather(*[engine.execute_one_case(run_id, cid) for cid in ids])
        return {"peak": peak}

    return asyncio.run(main())


def test_a_run_never_exceeds_its_concurrency(tmp_path) -> None:
    o = _run(str(tmp_path / "conc.db"))
    assert o["peak"] <= CONCURRENCY, (
        f"{o['peak']} browsers were open at once with 并发数={CONCURRENCY} — the setting "
        "must cap real browsers, not just the in-process fallback path"
    )
    assert o["peak"] > 0, "the stub never ran; the harness is broken, not the code"

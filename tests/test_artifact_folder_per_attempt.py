"""Runnable check: each attempt gets its own artifact folder.

Artifacts used to be keyed by case id (`runs/{case_id}/live-N.png`), so every re-run of
a case overwrote the previous run's screenshots, video and history. Old reports silently
rendered the newest run's frames — which is what made a VRS report show a DNS error page
next to a step that had clearly reached the app.

python -m pytest tests/test_artifact_folder_per_attempt.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")


def _two_runs(tmp_db: str) -> dict:
    """Run the SAME case twice and record the CaseSpec each attempt was given."""
    from cryptography.fernet import Fernet

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = Fernet.generate_key().decode()
    os.environ.pop("AUTH_ENABLED", None)

    import app.db as db
    import app.engine as engine
    import app.executor as executor
    from app.config import get_settings
    from app.models import Environment, Project, Run, RunResult, TestCase

    get_settings.cache_clear()
    db._engine = db._Session = None

    specs: list = []

    async def fake_execute_case(spec, on_step=None, **kw):  # noqa: ANN001
        specs.append(spec)
        return executor.ResultSpec(case_id=spec.case_id, status="passed")

    async def main() -> dict:
        await db.init_db()
        executor.execute_case = fake_execute_case

        async with db.db_session() as s:
            p = Project(name="VRS")
            s.add(p)
            await s.flush()
            s.add(Environment(project_id=p.id, name="test", is_default=True))
            case = TestCase(project_id=p.id, name="c1", prompt="do it")
            s.add(case)
            await s.flush()
            case_id = case.id
            run_ids = []
            for n in ("first", "second"):
                run = Run(project_id=p.id, name=n, case_ids=[case_id], total_count=1)
                s.add(run)
                await s.flush()
                run_ids.append(run.id)

        for run_id in run_ids:
            await engine.execute_one_case(run_id, case_id)

        async with db.db_session() as s:
            from sqlalchemy import select

            rows = (await s.execute(select(RunResult).order_by(RunResult.id))).scalars().all()
            return {
                "case_id": case_id,
                "result_ids": [r.id for r in rows],
                "spec_result_ids": [sp.result_id for sp in specs],
            }

    return asyncio.run(main())


def test_each_attempt_writes_to_its_own_folder(tmp_path) -> None:
    o = _two_runs(str(tmp_path / "art.db"))

    assert o["spec_result_ids"] == o["result_ids"], (
        "each attempt must be handed its own RunResult id — artifacts are stored under it"
    )
    assert len(set(o["spec_result_ids"])) == 2, (
        f"two runs of case {o['case_id']} shared an artifact folder "
        f"{o['spec_result_ids']} — the second run overwrites the first run's screenshots"
    )

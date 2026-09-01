"""Runnable check: the cases list carries each case's most recent verdict.

Without it the cases table answered "是否跑过 / 通过没有 / 什么时候跑的" with nothing at
all — you had to open every run report to find out whether a case was OK.

python -m pytest tests/test_case_last_result.py
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

    import app.db as db
    from app.config import get_settings
    from app.main import create_app
    from app.models import Project, Run, RunResult, TestCase
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()
    db._engine = db._Session = None

    async def main() -> dict:
        await db.init_db()
        async with db.db_session() as s:
            p = Project(name="VRS")
            s.add(p)
            await s.flush()
            ran = TestCase(project_id=p.id, name="ran twice", prompt="x")
            never = TestCase(project_id=p.id, name="never ran", prompt="x")
            s.add(ran)
            s.add(never)
            await s.flush()
            old = Run(project_id=p.id, name="old", case_ids=[ran.id], total_count=1)
            new = Run(project_id=p.id, name="new", case_ids=[ran.id], total_count=1)
            s.add(old)
            s.add(new)
            await s.flush()
            # the case passed once and then broke — the table must show the break
            s.add(RunResult(run_id=old.id, case_id=ran.id, status="passed"))
            s.add(RunResult(run_id=new.id, case_id=ran.id, status="failed"))
            pid, ran_id, never_id, new_id = p.id, ran.id, never.id, new.id

        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            rows = (await ac.get(f"/api/projects/{pid}/testcases")).json()
        return {
            "by_id": {r["id"]: r for r in rows},
            "ran_id": ran_id,
            "never_id": never_id,
            "new_id": new_id,
        }

    return asyncio.run(main())


def test_a_case_shows_its_newest_verdict_and_where_it_came_from(tmp_path) -> None:
    o = _run(str(tmp_path / "tp.db"))
    ran = o["by_id"][o["ran_id"]]
    never = o["by_id"][o["never_id"]]

    assert ran["last_status"] == "failed", (
        "the newest run wins — a stale pass must not hide a break"
    )
    assert ran["last_run_id"] == o["new_id"], "the badge links to the report that produced it"
    assert ran["last_run_at"], "the table shows when it last ran"

    # never run is a distinct state from failed, and the table has to say so
    assert never["last_status"] is None
    assert never["last_run_id"] is None
    assert never["last_run_at"] is None


if __name__ == "__main__":
    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_a_case_shows_its_newest_verdict_and_where_it_came_from(pathlib.Path(d))
    print("ok")

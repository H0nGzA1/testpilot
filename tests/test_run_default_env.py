"""Runnable check: a run with no explicit environment inherits the project's default.

base_url and the (env, role) -> account mapping both live on the Environment. A run
created with environment_id=None therefore matched no env-bound credential and the
case died with 角色「admin」没有可用账号 even though the account existed. Ad-hoc runs
(the Run button on the cases list) never send an environment, so that was every run.

python -m pytest tests/test_run_default_env.py
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
    from app.models import Environment, Project, Run, TestCase
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()
    db._engine = db._Session = None

    async def main() -> dict:
        await db.init_db()
        # never actually execute the suite — we only care about the Run row
        api._launch = lambda run_id: asyncio.sleep(0)
        out: dict = {}
        async with db.db_session() as s:
            p = Project(name="VRS", roles=["admin"])
            s.add(p)
            await s.flush()
            s.add(Environment(project_id=p.id, name="dev", base_url="http://dev", is_default=False))
            env = Environment(
                project_id=p.id, name="test", base_url="http://app.example.com", is_default=True
            )
            s.add(env)
            s.add(TestCase(project_id=p.id, name="c1", prompt="do a thing", role="admin"))
            await s.flush()
            out["pid"], out["env_id"] = p.id, env.id

        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post(f"/api/projects/{out['pid']}/runs", json={"name": "adhoc"})
            assert r.status_code < 400, r.text
            out["adhoc"] = r.json()

            r = await ac.post(f"/api/runs/{out['adhoc']['id']}/rerun")
            assert r.status_code < 400, r.text
            out["rerun"] = r.json()

        # a run that names an environment explicitly must keep it
        async with db.db_session() as s:
            run = await s.get(Run, out["adhoc"]["id"])
            run.environment_id = None  # simulate a pre-fix run row
        return out

    return asyncio.run(main())


def test_adhoc_run_inherits_the_default_environment(tmp_path) -> None:
    o = _run(str(tmp_path / "tp.db"))
    assert o["adhoc"]["environment_id"] == o["env_id"], (
        "an ad-hoc run must land on the default env, else env-bound accounts never match"
    )
    assert o["rerun"]["environment_id"] == o["env_id"], "a re-run must not drop the env"

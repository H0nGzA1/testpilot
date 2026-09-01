"""Runnable check: a case without a role reuses a captured session too.

A case WITH a role captured a session bundle from its password account once and restored
it, so it started logged in. A case WITHOUT a role got handed the username and password
instead and typed the login form on every case of every run — burning steps before it
could even reach the module under test (VRS TC-034…038). Both paths now capture once.

python -m pytest tests/test_roleless_session_reuse.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")

BUNDLE = '{"cookies": [{"name": "sid", "value": "abc"}]}'


def _run(tmp_db: str, with_role: bool) -> dict:
    """Drive execute_one_case with a stubbed executor and capture the CaseSpec it built."""
    from cryptography.fernet import Fernet

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = Fernet.generate_key().decode()
    os.environ.pop("AUTH_ENABLED", None)

    import app.db as db
    import app.engine as engine
    import app.executor as executor
    from app.config import get_settings
    from app.crypto import encrypt
    from app.models import Credential, Environment, Project, Run, TestCase

    get_settings.cache_clear()
    db._engine = db._Session = None

    specs: list = []
    captures: list[int] = []

    async def fake_execute_case(spec, on_step=None, **kw):  # noqa: ANN001
        specs.append(spec)
        return executor.ResultSpec(case_id=spec.case_id, status="passed")

    async def fake_ensure_bundle(cred_id, field, base_url, username, password, timeout_s, **kw):  # noqa: ANN001
        captures.append(cred_id)
        return BUNDLE

    async def main() -> dict:
        await db.init_db()
        executor.execute_case = fake_execute_case
        engine._ensure_bundle = fake_ensure_bundle

        async with db.db_session() as s:
            p = Project(name="VRS", roles=["admin"])
            s.add(p)
            await s.flush()
            env = Environment(
                project_id=p.id, name="test", base_url="http://app.example.com", is_default=True
            )
            s.add(env)
            await s.flush()
            cred = Credential(
                project_id=p.id,
                type="password",
                role="admin" if with_role else None,
                environment_id=env.id,
                label="admin",
                username="admin",
                secret=encrypt("pw"),
                is_active=True,
            )
            s.add(cred)
            case = TestCase(
                project_id=p.id,
                name="c1",
                prompt="open the park module",
                start_url="/visitor/master/park",
                role="admin" if with_role else None,
            )
            s.add(case)
            await s.flush()
            run = Run(
                project_id=p.id,
                name="r",
                case_ids=[case.id],
                total_count=1,
                environment_id=env.id,
            )
            s.add(run)
            await s.flush()
            run_id, case_id = run.id, case.id

        await engine.execute_one_case(run_id, case_id)
        spec = specs[0]
        return {
            "login_state": spec.login_state,
            "username": spec.login_username,
            "start_url": spec.start_url,
            "captures": captures,
        }

    return asyncio.run(main())


def test_a_roleless_case_starts_from_a_restored_session(tmp_path) -> None:
    o = _run(str(tmp_path / "norole.db"), with_role=False)

    assert o["login_state"] == BUNDLE, (
        "a role-less case must restore a captured session, not type the login form — "
        "the executor only injects the 'log in with …' instruction when login_state is empty"
    )
    assert len(o["captures"]) == 1, "the session is captured once and cached on the account"
    assert o["start_url"] == "http://app.example.com/visitor/master/park", (
        "and it should land straight on the module under test"
    )


def test_a_role_case_still_works_the_same_way(tmp_path) -> None:
    o = _run(str(tmp_path / "role.db"), with_role=True)
    assert o["login_state"] == BUNDLE
    assert len(o["captures"]) == 1

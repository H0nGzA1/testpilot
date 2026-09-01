"""Runnable check for the guided-flow flag on the user row.

The flag decides whether the full-screen first-run flow opens, so the two things
that matter are: existing users start NULL (everyone gets it once, which is the
whole point of shipping it), and marking it is idempotent — reopening the guide
from the sidebar and dismissing it again must not move the original timestamp.

python -m pytest tests/test_onboarding_flag.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

import pytest

pytest.importorskip("aiosqlite")


def _instant(iso: str) -> datetime:
    """Compare timestamps as instants, not strings. SQLite drops the offset on a
    DateTime(timezone=True) round-trip, so the value returned inside the marking
    request is tz-aware while the same value read back is naive; on Postgres both
    carry the offset. Nothing depends on the format — the frontend only checks
    whether the field is set."""
    return datetime.fromisoformat(iso).replace(tzinfo=None)


def _run(tmp_db: str) -> dict:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = "x" * 32
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["JWT_SECRET"] = "y" * 32

    import app.db as db
    from app.config import get_settings
    from app.main import create_app
    from app.models import User
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()
    db._engine = db._Session = None

    async def main() -> dict:
        from app import auth

        await db.init_db()
        out: dict = {}
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            # a user that predates the feature: the column is simply NULL
            async with db.db_session() as s:
                s.add(User(email="a@b.c", name="A", password_hash=auth.hash_password("pw")))

            r = await ac.post("/api/auth/login", json={"email": "a@b.c", "password": "pw"})
            assert r.status_code < 400, r.text
            out["login"] = r.json()

            out["me_before"] = (await ac.get("/api/auth/me")).json()

            out["mark"] = (await ac.post("/api/auth/onboarded")).json()
            out["me_after"] = (await ac.get("/api/auth/me")).json()

            # dismissing a second time (reopened from the sidebar) must not re-stamp
            out["mark_again"] = (await ac.post("/api/auth/onboarded")).json()
        return out

    return asyncio.run(main())


def test_onboarded_flag_lifecycle(tmp_path) -> None:
    o = _run(str(tmp_path / "tp.db"))

    # every existing user is un-onboarded, so the guide opens for them once
    assert o["login"]["onboarded_at"] is None
    assert o["me_before"]["onboarded_at"] is None

    stamped = o["mark"]["onboarded_at"]
    assert stamped is not None, "dismissing the guide must record it"
    assert _instant(o["me_after"]["onboarded_at"]) == _instant(stamped), (
        "/auth/me must reflect it immediately"
    )

    assert _instant(o["mark_again"]["onboarded_at"]) == _instant(stamped), (
        "marking twice must not move the timestamp"
    )


def test_onboarded_is_a_noop_without_a_session(tmp_path) -> None:
    """Auth-disabled instances have no user at all; the endpoint must not 500 — the
    frontend keeps the flag in localStorage there."""
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'anon.db'}"
    os.environ["TESTPILOT_SECRET_KEY"] = "x" * 32
    os.environ.pop("AUTH_ENABLED", None)

    import app.db as db
    from app.config import get_settings
    from app.main import create_app
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()
    db._engine = db._Session = None

    async def main() -> dict:
        await db.init_db()
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post("/api/auth/onboarded")
            assert r.status_code < 400, r.text
            return r.json()

    assert asyncio.run(main()) == {"onboarded_at": None}

"""Runnable check for the password-reset loop (admin reset, forgot-password, self-serve
change).

Reset links are stateless JWTs — there is no tokens table — so the properties that
actually keep them safe are the ones asserted here: single use (a spent link is dead,
because it is bound to the password hash it was minted against), no account enumeration
from /auth/forgot, and a reset token cannot be pasted in as a session cookie.

python -m pytest tests/test_password_reset.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")


def _link_path(link: str) -> str:
    """The reset link as the SPA route (PUBLIC_BASE_URL is unset in tests)."""
    return link.split("/reset/")[-1]


def _run(tmp_db: str) -> dict:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = "x" * 32
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["JWT_SECRET"] = "y" * 32

    import app.db as db
    from app import auth, mailer
    from app.config import get_settings
    from app.main import create_app
    from app.models import User
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()
    db._engine = db._Session = None

    sent: list[tuple[str, str]] = []

    async def _fake_send(to: str, subject: str, body: str) -> bool:
        sent.append((to, body))
        return True

    mailer.send_email = _fake_send  # the relay is not reachable from tests

    async def main() -> dict:
        await db.init_db()
        out: dict = {"sent": sent}
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            async with db.db_session() as s:
                s.add(
                    User(
                        email="admin@b.c",
                        password_hash=auth.hash_password("adminpw"),
                        is_admin=True,
                    )
                )
                s.add(User(email="pandas@b.c", password_hash=auth.hash_password("oldpw")))

            # --- an admin issues a reset link for a locked-out user ---
            await ac.post("/api/auth/login", json={"email": "admin@b.c", "password": "adminpw"})
            users = (await ac.get("/api/admin/users")).json()
            uid = next(u["id"] for u in users if u["email"] == "pandas@b.c")
            r = await ac.post(f"/api/admin/users/{uid}/reset-password")
            assert r.status_code < 400, r.text
            token = _link_path(r.json()["link"])
            out["admin_issue"] = r.json()
            await ac.post("/api/auth/logout")

            # a reset token is not a session token
            ac.cookies.set(auth.COOKIE_NAME, token)
            out["token_as_cookie"] = (await ac.get("/api/auth/me")).json()
            ac.cookies.clear()

            # --- the user redeems it and lands signed in ---
            r = await ac.post("/api/auth/reset", json={"token": token, "password": "newpw1"})
            out["reset_status"] = r.status_code
            out["reset_user"] = r.json()
            out["me_after_reset"] = (await ac.get("/api/auth/me")).json()

            # the same link a second time is dead, and so is the old password
            out["replay_status"] = (
                await ac.post("/api/auth/reset", json={"token": token, "password": "hijack"})
            ).status_code
            await ac.post("/api/auth/logout")
            out["old_pw_status"] = (
                await ac.post("/api/auth/login", json={"email": "pandas@b.c", "password": "oldpw"})
            ).status_code
            out["new_pw_status"] = (
                await ac.post("/api/auth/login", json={"email": "pandas@b.c", "password": "newpw1"})
            ).status_code

            # --- self-serve change, signed in as pandas ---
            out["change_wrong_old"] = (
                await ac.post(
                    "/api/auth/change-password",
                    json={"old_password": "nope", "new_password": "newpw2"},
                )
            ).status_code
            out["change_ok"] = (
                await ac.post(
                    "/api/auth/change-password",
                    json={"old_password": "newpw1", "new_password": "newpw2"},
                )
            ).status_code
            await ac.post("/api/auth/logout")
            out["login_after_change"] = (
                await ac.post("/api/auth/login", json={"email": "pandas@b.c", "password": "newpw2"})
            ).status_code

            # --- forgot-password: same answer whether or not the account exists ---
            sent.clear()
            out["forgot_known"] = (
                await ac.post("/api/auth/forgot", json={"email": "pandas@b.c"})
            ).json()
            out["mails_known"] = len(sent)
            out["forgot_unknown"] = (
                await ac.post("/api/auth/forgot", json={"email": "nobody@b.c"})
            ).json()
            out["mails_total"] = len(sent)
            # a second request inside the throttle window sends nothing
            out["forgot_repeat"] = (
                await ac.post("/api/auth/forgot", json={"email": "pandas@b.c"})
            ).json()
            out["mails_after_repeat"] = len(sent)
        return out

    return asyncio.run(main())


def test_password_reset_loop(tmp_path) -> None:
    o = _run(str(tmp_path / "tp.db"))

    assert o["admin_issue"]["email"] == "pandas@b.c"
    assert o["admin_issue"]["emailed"] is True
    assert "/reset/" in o["admin_issue"]["link"], "admins get a copyable link, not a password"

    assert o["token_as_cookie"] is None, "a reset token must not work as a session cookie"

    assert o["reset_status"] < 400, o["reset_user"]
    assert o["me_after_reset"]["email"] == "pandas@b.c", "redeeming a link signs you in"

    assert o["replay_status"] == 400, "a spent reset link must not work twice"
    assert o["old_pw_status"] == 401, "the old password must stop working"
    assert o["new_pw_status"] < 400

    assert o["change_wrong_old"] == 400, "changing a password needs the current one"
    assert o["change_ok"] < 400
    assert o["login_after_change"] < 400

    assert o["forgot_known"] == {"ok": True}
    assert o["forgot_unknown"] == {"ok": True}, "must not reveal that an account is missing"
    assert o["mails_known"] == 1
    assert o["mails_total"] == 1, "no mail for an address without an account"
    assert o["forgot_repeat"] == {"ok": True}
    assert o["mails_after_repeat"] == 1, "throttled: no second mail inside the window"

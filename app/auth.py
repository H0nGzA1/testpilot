"""Auth core: password hashing (bcrypt), session JWTs, and current-user helpers.

Enforcement is gated by settings.auth_enabled — while False the app stays no-login
and require_user() is a no-op, so auth can land before the login UI ships.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request

from app.config import get_settings
from app.db import db_session
from app.models import User

COOKIE_NAME = "tp_session"
RESET_TTL_HOURS = 2


def _secret() -> str:
    s = get_settings()
    return s.jwt_secret or s.secret_key or "tp-dev-insecure-secret"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def new_invite_token() -> str:
    return secrets.token_urlsafe(32)[:64]


def create_session_token(user_id: int) -> str:
    exp = datetime.now(UTC) + timedelta(hours=get_settings().jwt_ttl_hours)
    return jwt.encode({"sub": str(user_id), "exp": exp}, _secret(), algorithm="HS256")


def _decode(token: str) -> int | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
        # Non-session tokens (password resets) are signed with the same secret — refuse
        # them here, or a reset link pasted into the cookie would be a free login.
        if payload.get("typ"):
            return None
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def pw_fingerprint(password_hash: str | None) -> str:
    """Short digest of the stored hash. A reset token carries the fingerprint of the
    password it was issued against, so the first use — which changes the hash — burns
    that token and every other outstanding one. Single-use without a tokens table."""
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:16]


def create_reset_token(user: User) -> str:
    exp = datetime.now(UTC) + timedelta(hours=RESET_TTL_HOURS)
    return jwt.encode(
        {
            "sub": str(user.id),
            "typ": "pwreset",
            "pwf": pw_fingerprint(user.password_hash),
            "exp": exp,
        },
        _secret(),
        algorithm="HS256",
    )


def decode_reset_token(token: str) -> tuple[int, str] | None:
    """(user_id, password fingerprint) for a valid, unexpired reset token, else None."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
        if payload.get("typ") != "pwreset":
            return None
        return int(payload["sub"]), str(payload["pwf"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


async def current_user(request: Request) -> User | None:
    """The logged-in user from the session cookie, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    uid = _decode(token)
    if uid is None:
        return None
    async with db_session() as s:
        u = await s.get(User, uid)
        return u if (u and u.is_active) else None


async def require_user(request: Request) -> User | None:
    """FastAPI dependency: enforce login when auth_enabled, else pass through."""
    u = await current_user(request)
    if get_settings().auth_enabled and u is None:
        raise HTTPException(401, "authentication required")
    return u


async def require_admin(request: Request) -> User | None:
    u = await require_user(request)
    if get_settings().auth_enabled and (u is None or not u.is_admin):
        raise HTTPException(403, "admin only")
    return u

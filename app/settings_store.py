"""Admin-managed system settings (app_setting table). Secret values are encrypted
at rest with the same Fernet key as credentials and never returned in plaintext by
the API — only read server-side (e.g. the global GitLab token for sync)."""

from __future__ import annotations

from app.crypto import decrypt, encrypt, secret_configured
from app.models import AppSetting

GITLAB_TOKEN_KEY = "gitlab_token"


async def get_setting(session, key: str) -> str | None:
    row = await session.get(AppSetting, key)
    if row is None or not row.value:
        return None
    if row.secret:
        return decrypt(row.value) if secret_configured() else None
    return row.value


async def set_setting(session, key: str, value: str, *, secret: bool = False) -> None:
    stored = encrypt(value) if (secret and value and secret_configured()) else value
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=stored, secret=secret))
    else:
        row.value = stored
        row.secret = secret


async def has_setting(session, key: str) -> bool:
    row = await session.get(AppSetting, key)
    return row is not None and bool(row.value)

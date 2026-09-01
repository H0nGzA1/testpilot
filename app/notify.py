"""Notifications: write an in-app Notification row and (best-effort) email the user.

Callers pass a ready-made title/body/link; `push` resolves the user's email, sends the
mail (never raising), and records `emailed` so a backfill won't double-send. The caller's
session owns the transaction — push only adds rows / awaits the SMTP handoff.
"""

from __future__ import annotations

from app import mailer
from app.config import get_settings
from app.models import Notification, User


def _abs(link: str | None) -> str | None:
    if not link:
        return None
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}{link}" if base and link.startswith("/") else link


async def push(
    session,
    *,
    user_id: int | None,
    type: str,
    title: str,
    body: str = "",
    link: str | None = None,
    suite_id: int | None = None,
    run_id: int | None = None,
    issue_id: int | None = None,
    send_email: bool = True,
) -> None:
    """Notify one user. No-op when user_id is None (unassigned)."""
    if user_id is None:
        return
    user = await session.get(User, user_id)
    emailed = False
    if send_email and user is not None and user.is_active and user.email:
        url = _abs(link)
        mail_body = body + (f"\n\n{url}" if url else "")
        emailed = await mailer.send_email(user.email, f"[TestPilot] {title}", mail_body)
    session.add(
        Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            link=link,
            suite_id=suite_id,
            run_id=run_id,
            issue_id=issue_id,
            emailed=emailed,
        )
    )

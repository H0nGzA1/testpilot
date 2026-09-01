"""System SMTP sender (invite emails). Sends from a
fixed system address via an SMTP relay (port 25, unauthenticated by default);
SSL/STARTTLS/login stay config-gated for other deployments. Best-effort — a send
failure is logged, never raised, so an invite still returns its copyable link."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

from app.config import get_settings

log = logging.getLogger("testpilot.mailer")


def _send_sync(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = s.email_from
    msg["To"] = to
    client = (
        smtplib.SMTP_SSL(s.email_host, s.email_port, timeout=15)
        if s.email_use_ssl
        else smtplib.SMTP(s.email_host, s.email_port, timeout=15)
    )
    try:
        if s.email_use_tls:
            client.starttls()
        if s.email_host_user:
            client.login(s.email_host_user, s.email_host_password)
        client.sendmail(s.email_from, [to], msg.as_string())
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 - quit best-effort; the send already happened
            pass


async def send_email(to: str, subject: str, body: str) -> bool:
    """Returns True if the SMTP handoff succeeded, False otherwise (never raises)."""
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
        return True
    except Exception:
        log.warning("invite email to %s failed (relay unreachable?)", to, exc_info=True)
        return False


def invite_email_body(inviter: str, link: str) -> tuple[str, str]:
    subject = "TestPilot 邀请 / You've been invited to TestPilot"
    body = (
        f"{inviter} 邀请你加入 TestPilot 测试平台。\n\n"
        f"点击链接设置密码并激活账号(有效期 7 天):\n{link}\n\n"
        f"{inviter} invited you to TestPilot. Open the link to set your password:\n{link}\n"
    )
    return subject, body

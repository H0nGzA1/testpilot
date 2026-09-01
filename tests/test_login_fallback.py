"""Runnable check: the agent always has the real credentials, and a stale session expires.

VRS run 42 lost 30 cases to one dead session. The bundle cached on the account was a day
old, so restoring it dropped every case on the login page — and because a bundle existed,
the executor withheld the username and password. The agent then either gave up
(「无法完成任务，因为缺少登录凭据」) or invented one (it tried `password123`), and the
repeated attempts tripped the app's 「请求过于频繁」 rate limit for the whole run.

python -m pytest tests/test_login_fallback.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine import bundle_is_fresh
from app.executor import CaseSpec, build_task

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _spec(**kw) -> CaseSpec:
    return CaseSpec(case_id=1, prompt="open the park module", **kw)


def test_credentials_are_offered_even_with_a_restored_session() -> None:
    task = build_task(
        _spec(login_state='{"cookies": []}', login_username="admin", login_password="s3cret"),
        "Chinese",
    )
    assert "admin" in task and "s3cret" in task, (
        "a restored session can be dead — without the credentials the agent guesses"
    )
    assert "never invent credentials" in task


def test_credentials_are_still_offered_without_a_session() -> None:
    task = build_task(_spec(login_username="admin", login_password="s3cret"), "Chinese")
    assert "admin" in task and "s3cret" in task


def test_no_account_means_no_login_instruction() -> None:
    task = build_task(_spec(login_state='{"cookies": []}'), "Chinese")
    assert "log in with" not in task


def test_start_url_and_task_survive_the_split() -> None:
    task = build_task(_spec(start_url="http://app.example.com/visitor/master/park"), "Chinese")
    assert task.startswith("First go to http://app.example.com/visitor/master/park.")
    assert "open the park module" in task
    assert "Chinese" in task


def test_a_stale_bundle_is_not_trusted() -> None:
    assert bundle_is_fresh(NOW + timedelta(minutes=1), now=NOW) is True
    assert bundle_is_fresh(NOW - timedelta(minutes=1), now=NOW) is False, (
        "an expired bundle must be re-captured, not restored onto a login page"
    )
    # no recorded expiry means it predates expiry tracking, so it is old by definition —
    # trusting it is exactly what handed run 44's 16 browsers a day-old dead session
    assert bundle_is_fresh(None, now=NOW) is False
    # sqlite drops the offset on round-trip; a naive value must still compare as UTC
    assert bundle_is_fresh((NOW - timedelta(hours=1)).replace(tzinfo=None), now=NOW) is False

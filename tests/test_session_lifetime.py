"""Runnable check: a captured login is re-used only while the app-side session lives.

Run 44's remaining login failures came from modelling the session wrong. The bundle was
trusted for 8 hours while the app under test forgets a session in about 30 minutes, so
cases restored a corpse and landed on the login page — and because the rate limit there is
per account, the resulting burst of logins locked the account out for the rest of the run.

python -m pytest tests/test_session_lifetime.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine import RECAPTURE_COOLDOWN_S, bundle_is_fresh, captured_recently

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
TTL = timedelta(minutes=25)
CASE_TIMEOUT = 600  # 10 minutes


def test_a_bundle_that_dies_mid_case_is_not_handed_out() -> None:
    """The point of min_remaining_s: a case must not start on a session that expires while
    it is running. Otherwise it drops onto a login page halfway through."""
    assert bundle_is_fresh(NOW + timedelta(minutes=20), now=NOW, min_remaining_s=CASE_TIMEOUT)
    assert not bundle_is_fresh(NOW + timedelta(minutes=5), now=NOW, min_remaining_s=CASE_TIMEOUT), (
        "5 minutes of session left is not enough for a 10 minute case"
    )
    # still valid, just not for long enough — without min_remaining_s this would pass
    assert bundle_is_fresh(NOW + timedelta(minutes=5), now=NOW)


def test_an_undated_or_expired_bundle_is_never_trusted() -> None:
    assert not bundle_is_fresh(None, now=NOW)
    assert not bundle_is_fresh(NOW - timedelta(seconds=1), now=NOW)
    # sqlite drops the offset on round-trip; a naive value must still compare as UTC
    assert not bundle_is_fresh((NOW - timedelta(hours=1)).replace(tzinfo=None), now=NOW)


def test_a_burst_of_self_heals_collapses_into_one_login() -> None:
    """Every case of a run notices the same dead session at once. Only the first should
    log in; the rest must take the bundle it just captured, or the per-account rate limit
    locks everyone out."""
    just_captured = NOW + TTL - timedelta(seconds=5)  # captured 5s ago
    assert captured_recently(just_captured, TTL, RECAPTURE_COOLDOWN_S, now=NOW)

    older = NOW + TTL - timedelta(seconds=RECAPTURE_COOLDOWN_S + 60)
    assert not captured_recently(older, TTL, RECAPTURE_COOLDOWN_S, now=NOW), (
        "a genuinely old capture must still be refreshable — the cooldown is a herd guard, "
        "not a lock on ever logging in again"
    )
    assert not captured_recently(None, TTL, RECAPTURE_COOLDOWN_S, now=NOW)


def test_the_cooldown_is_shorter_than_the_session() -> None:
    """A cooldown longer than the session would deadlock: the bundle expires, everyone
    needs a new one, and nobody is allowed to capture it."""
    assert timedelta(seconds=RECAPTURE_COOLDOWN_S) < TTL

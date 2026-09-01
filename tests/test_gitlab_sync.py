"""Mapping-layer tests for GitLab issue sync (pure functions, no network)."""

import pytest

from app.gitlab_sync import (
    labels_to_severity,
    labels_to_status,
    passthrough_labels,
    state_event_for,
    status_to_labels,
    sync_hash,
)


@pytest.mark.unit
def test_status_to_labels_carries_scoped_and_passthrough():
    labels = status_to_labels("in_progress", "high", ["regression", "status::old", "severity::low"])
    assert "status::in_progress" in labels
    assert "severity::high" in labels
    assert "regression" in labels
    # old scoped labels are dropped, not duplicated
    assert "status::old" not in labels
    assert "severity::low" not in labels


@pytest.mark.unit
@pytest.mark.parametrize(
    "status,expected",
    [
        ("open", "reopen"),
        ("in_progress", "reopen"),
        ("fixed", "reopen"),
        ("verified", "close"),
        ("closed", "close"),
    ],
)
def test_state_event_for(status, expected):
    assert state_event_for(status) == expected


@pytest.mark.unit
def test_labels_to_status_prefers_scoped_label():
    assert labels_to_status(["status::verified", "x"], "opened") == "verified"


@pytest.mark.unit
def test_labels_to_status_derives_from_state_when_no_label():
    assert labels_to_status(["x"], "closed") == "closed"
    assert labels_to_status(["x"], "opened") == "open"


@pytest.mark.unit
def test_labels_to_severity_falls_back_to_default():
    assert labels_to_severity(["severity::critical"], "medium") == "critical"
    assert labels_to_severity(["x"], "medium") == "medium"


@pytest.mark.unit
def test_passthrough_strips_scoped():
    assert passthrough_labels(["a", "status::x", "severity::y", "b"]) == ["a", "b"]


@pytest.mark.unit
def test_sync_hash_ignores_scoped_labels_and_order():
    # same passthrough set, different order + scoped noise -> identical hash
    a = sync_hash("t", "open", "high", ["b", "a", "status::open"])
    b = sync_hash("t", "open", "high", ["a", "b"])
    assert a == b
    # a real change flips it
    assert sync_hash("t", "closed", "high", ["a", "b"]) != a

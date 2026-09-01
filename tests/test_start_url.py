"""Runnable check: a case's start_url is resolved against the environment.

Cases are written once and run against dev/test/prod, so their start_url is a path like
/visitor/master/park. It used to reach the browser bare: Chromium read it as
http://localhost/visitor/master/park, got ERR_CONNECTION_REFUSED, and the agent went
looking for the app on a search engine (VRS run 39, five cases wasted).

python -m pytest tests/test_start_url.py
"""

from __future__ import annotations

import pytest

from app.engine import resolve_start_url

BASE = "http://app.example.com"


@pytest.mark.parametrize(
    ("start_url", "base", "expected"),
    [
        # the bug: a path must land on the environment, never on localhost
        ("/visitor/master/park", BASE, "http://app.example.com/visitor/master/park"),
        ("visitor/master/park", BASE, "http://app.example.com/visitor/master/park"),
        # an absolute start_url wins — some cases deliberately target another host
        ("https://other.example.com/x", BASE, "https://other.example.com/x"),
        ("http://other.example.com/x", BASE, "http://other.example.com/x"),
        # no start_url => open the environment root, as before
        (None, BASE, BASE),
        ("", BASE, BASE),
        # a base_url with a path: a rooted path replaces it, per URL semantics
        ("/park", "http://app.example.com/app/", "http://app.example.com/park"),
        # nothing to join onto: pass it through rather than inventing a host
        ("/park", None, "/park"),
        (None, None, None),
    ],
)
def test_resolve_start_url(start_url, base, expected) -> None:
    assert resolve_start_url(start_url, base) == expected


def test_a_bare_path_never_resolves_to_localhost() -> None:
    """The actual failure mode, stated as its own guard."""
    resolved = resolve_start_url("/visitor/master/park", BASE)
    assert resolved is not None and "localhost" not in resolved
    assert resolved.startswith(BASE)

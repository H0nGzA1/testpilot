"""The storage-seed init script must only write keys that are absent.

It runs on EVERY new document, so an unconditional setItem re-writes values the app
itself just updated — the app under test compares localStorage.DVADMIN3_VERSION against /version-build
and reload()s on a mismatch, so re-seeding the stale version reloaded the page ~19x/s
forever (blank DOM + hung CDP screenshots). Runs without a browser/DB.
"""

from __future__ import annotations

import asyncio
import json

import pytest


class _FakeBrowser:
    """Records what _restore_session injects."""

    def __init__(self) -> None:
        self.script: str | None = None
        self.cookies: list | None = None

    async def start(self) -> None:
        pass

    async def _cdp_set_cookies(self, cookies) -> None:
        self.cookies = cookies

    async def _cdp_add_init_script(self, script: str) -> None:
        self.script = script


@pytest.mark.unit
def test_seed_writes_only_absent_keys() -> None:
    from app.executor import _restore_session

    bundle = json.dumps(
        {
            "cookies": [{"name": "sid", "value": "abc"}],
            "origins": [
                {
                    "origin": "https://your-app.example.com",
                    "localStorage": [{"name": "DVADMIN3_VERSION", "value": "3.2.0.old"}],
                    "sessionStorage": [{"name": "token", "value": "jwt"}],
                }
            ],
        }
    )
    b = _FakeBrowser()
    asyncio.run(_restore_session(b, bundle))

    assert b.cookies == [{"name": "sid", "value": "abc"}]
    seed = b.script or ""
    assert "3.2.0.old" in seed and "jwt" in seed  # values are carried
    # every write is guarded by an absence check — no unconditional overwrite
    assert seed.count("setItem") == seed.count("getItem")
    assert seed.count("===null") == seed.count("setItem")

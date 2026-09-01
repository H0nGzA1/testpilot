"""Runnable check for the Overview setup-checklist fields on GET /projects/{pid}/stats.

The checklist is derived from live state (no stored "onboarding done" flag), so these
fields ARE the feature — the one that matters is that a stale credential must not tick
the "add a working account" item.

python -m pytest tests/test_stats_checklist.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")


def _stats(tmp_db: str) -> list[dict]:
    """Drive the real ASGI app against a throwaway sqlite file; return three snapshots."""
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ.setdefault("TESTPILOT_SECRET_KEY", "x" * 32)

    # imported here so the env vars above are in place before settings are read
    import app.db as db
    from app.config import get_settings
    from app.main import create_app
    from app.models import Credential, Issue, Project, TestCase
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()  # settings are lru_cached; pick up the DATABASE_URL above
    db._engine = db._Session = None  # drop any engine bound to another DATABASE_URL

    async def main() -> list[dict]:
        await db.init_db()
        snaps = []
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            async with db.db_session() as s:
                s.add(Project(name="p"))  # bare project: nothing configured

            snaps.append((await ac.get("/api/projects/1/stats")).json())

            async with db.db_session() as s:
                (await s.get(Project, 1)).base_url = "https://example.com"
                s.add(
                    Credential(project_id=1, type="password", label="a", secret="x", healthy=False)
                )
                s.add(TestCase(project_id=1, name="c", prompt="do it"))
                s.add(Issue(project_id=1, title="i"))

            snaps.append((await ac.get("/api/projects/1/stats")).json())

            async with db.db_session() as s:
                s.add(
                    Credential(
                        project_id=1, type="storage_state", label="b", secret="y", healthy=True
                    )
                )

            snaps.append((await ac.get("/api/projects/1/stats")).json())
        return snaps

    return asyncio.run(main())


def _wizard(tmp_db: str) -> dict:
    """Replay exactly the HTTP calls NewProjectWizard makes on its happy path, and
    return the resulting stats — i.e. what the Overview checklist would then show."""
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ.setdefault("TESTPILOT_SECRET_KEY", "x" * 32)

    import app.db as db
    from app.config import get_settings
    from app.main import create_app
    from httpx import ASGITransport, AsyncClient

    get_settings.cache_clear()
    db._engine = db._Session = None

    async def main() -> dict:
        await db.init_db()
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            # step 1 — create the project
            r = await ac.post(
                "/api/projects", json={"name": "P", "base_url": "https://example.com"}
            )
            assert r.status_code < 400, r.text
            pid = r.json()["id"]

            # step 3 — the starter smoke case (this exact minimal body is what the
            # wizard sends; if TestCaseIn ever gains a required field, this fails here)
            r = await ac.post(
                f"/api/projects/{pid}/testcases",
                json={
                    "name": "Smoke — home page loads",
                    "prompt": "Open https://example.com and wait for the home page to finish loading.",
                    "expected": "The main content is rendered — no error page, no blank screen.",
                    "type": "smoke",
                    "tags": ["smoke"],
                },
            )
            assert r.status_code < 400, r.text
            case = r.json()
            assert case["type"] == "smoke" and case["tags"] == ["smoke"], case
            assert case["enabled"] is True, "the starter case must be runnable straight away"

            return (await ac.get(f"/api/projects/{pid}/stats")).json()

    return asyncio.run(main())


def test_wizard_happy_path_leaves_two_items_ticked(tmp_path) -> None:
    st = _wizard(str(tmp_path / "tp.db"))
    assert st["base_url"] == "https://example.com"  # item 1
    assert st["case_count"] == 1  # item 3
    assert st["has_healthy_credential"] is False  # item 2 — skipped in this path
    assert st["run_count"] == 0  # item 4 — still the user's next action


def test_setup_checklist_fields(tmp_path) -> None:
    fresh, stale, healthy = _stats(str(tmp_path / "tp.db"))

    assert fresh["base_url"] is None
    assert fresh["has_credential"] is False
    assert fresh["has_healthy_credential"] is False
    assert (fresh["case_count"], fresh["run_count"], fresh["issue_count"]) == (0, 0, 0)

    assert stale["base_url"] == "https://example.com"
    assert stale["has_credential"] is True
    assert stale["has_healthy_credential"] is False, "a stale session must not tick the item"
    assert (stale["case_count"], stale["issue_count"]) == (1, 1)

    assert healthy["has_healthy_credential"] is True


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_setup_checklist_fields(__import__("pathlib").Path(d))
    print("ok")

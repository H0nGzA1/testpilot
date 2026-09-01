"""Runnable check: optional integrations are off by default, and the platform's
underlying LLM model resolves from admin overrides (AppSetting) over env values.

python -m pytest tests/test_feature_flags.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("aiosqlite")


def _fresh(tmp_db: str):
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TESTPILOT_SECRET_KEY"] = "x" * 32
    os.environ.pop("ENABLE_GITLAB", None)
    os.environ.pop("ENABLE_FEISHU", None)
    os.environ["FEISHU_APP_ID"] = "cli_env_configured"
    os.environ["FEISHU_APP_SECRET"] = "shhh"
    os.environ["GATEWAY_MODEL"] = "env-model"

    import app.db as db
    from app.config import get_settings

    get_settings.cache_clear()
    db._engine = db._Session = None
    return db


def test_integrations_default_off_and_choke_points(tmp_path) -> None:
    db = _fresh(str(tmp_path / "t.db"))

    from app.config import get_settings
    from app.feishu import resolve_config

    s = get_settings()
    assert s.enable_gitlab is False and s.enable_feishu is False

    async def main() -> None:
        await db.init_db()
        async with db.db_session() as sess:
            cfg = await resolve_config(sess)
        # disabled => unconfigured, even though env has credentials: every feishu
        # path (notify/ws/webhook) no-ops on the empty app_id
        assert cfg["app_id"] == "" and cfg["app_secret"] == ""

    asyncio.run(main())


def test_llm_config_prefers_admin_overrides(tmp_path) -> None:
    db = _fresh(str(tmp_path / "t2.db"))

    import app.llm as llm
    from app.settings_store import set_setting

    async def main() -> None:
        await db.init_db()
        llm.invalidate_llm_cache()
        cfg = await llm.llm_config()
        assert cfg.model == "env-model"  # no overrides yet -> env

        async with db.db_session() as sess:
            await set_setting(sess, llm.LLM_MODEL_KEY, "admin-model")
            await set_setting(sess, llm.LLM_API_KEY_KEY, "sk-admin", secret=True)
        llm.invalidate_llm_cache()
        cfg = await llm.llm_config()
        assert cfg.model == "admin-model" and cfg.api_key == "sk-admin"

        # clearing the override falls back to env
        async with db.db_session() as sess:
            await set_setting(sess, llm.LLM_MODEL_KEY, "")
        llm.invalidate_llm_cache()
        assert (await llm.llm_config()).model == "env-model"

    asyncio.run(main())

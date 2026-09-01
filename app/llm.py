"""LLM clients (OpenAI-compatible gateway).

Base URL / API key / models resolve from admin-managed AppSetting overrides
(System settings → LLM model) with the env values as fallback, so the platform's
underlying model can be changed at runtime without a redeploy. Overrides are
cached per process for a short TTL; workers pick up changes on their next case.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from app.config import get_settings

# AppSetting keys (written by PUT /admin/settings/llm)
LLM_BASE_URL_KEY = "llm_base_url"
LLM_API_KEY_KEY = "llm_api_key"  # stored encrypted
LLM_MODEL_KEY = "llm_model"
LLM_AGENT_MODEL_KEY = "llm_agent_model"
_KEYS = (LLM_BASE_URL_KEY, LLM_API_KEY_KEY, LLM_MODEL_KEY, LLM_AGENT_MODEL_KEY)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str  # judge + default agent model
    agent_model: str  # "" => use model


_cached: LLMConfig | None = None
_cached_at: float = 0.0
_TTL_S = 30.0  # ponytail: pull-based refresh; push invalidation across processes if 30s lag hurts


def invalidate_llm_cache() -> None:
    """Drop this process's cache (called after an admin update)."""
    global _cached
    _cached = None


async def llm_config() -> LLMConfig:
    """Effective LLM config: AppSetting overrides over env defaults, briefly cached."""
    global _cached, _cached_at
    if _cached is not None and time.monotonic() - _cached_at < _TTL_S:
        return _cached
    s = get_settings()
    over: dict[str, str | None] = {}
    try:
        from app.db import db_session
        from app.settings_store import get_setting

        async with db_session() as sess:
            for key in _KEYS:
                over[key] = await get_setting(sess, key)
    except Exception:  # DB unavailable (early boot, bare tests) -> env values only
        over = {}
    _cached = LLMConfig(
        base_url=over.get(LLM_BASE_URL_KEY) or s.gateway_base_url,
        api_key=over.get(LLM_API_KEY_KEY) or s.gateway_api_key,
        model=over.get(LLM_MODEL_KEY) or s.gateway_model,
        agent_model=over.get(LLM_AGENT_MODEL_KEY) or s.agent_model,
    )
    _cached_at = time.monotonic()
    return _cached


async def openai_client() -> AsyncOpenAI:
    """Async OpenAI client for the judge. verify=False tolerates a self-signed gateway cert."""
    s = get_settings()
    cfg = await llm_config()
    http = httpx.AsyncClient(verify=s.gateway_verify_ssl, timeout=60)
    return AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key, http_client=http)


async def browser_use_llm():
    """LLM handed to the browser-use Agent. Imported lazily so `app.engine` stays import-safe."""
    from browser_use import ChatOpenAI

    s = get_settings()
    cfg = await llm_config()
    # browser-use's ChatOpenAI passes http_client straight to AsyncOpenAI; use it to
    # tolerate the gateway's self-signed cert (verify=False), same as the judge client.
    http = httpx.AsyncClient(verify=s.gateway_verify_ssl, timeout=120)
    return ChatOpenAI(
        # browser-use agent can run a different (e.g. local VLM) model than the judge;
        # falls back to the shared model when no agent model is set.
        model=cfg.agent_model or cfg.model,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        http_client=http,
        # complex pages produce long structured output; the 4096 default truncates it
        # into invalid JSON. raise the ceiling and also put the schema in the system
        # prompt so the model reliably returns the right shape.
        max_completion_tokens=s.gateway_max_tokens,
        add_schema_to_system_prompt=True,
    )

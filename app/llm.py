"""LLM clients pointed at the LLM gateway (OpenAI-compatible, self-signed cert)."""

from __future__ import annotations

import httpx
from openai import AsyncOpenAI

from app.config import get_settings


def openai_client() -> AsyncOpenAI:
    """Async OpenAI client for the judge. verify=False tolerates the self-signed gateway cert."""
    s = get_settings()
    http = httpx.AsyncClient(verify=s.gateway_verify_ssl, timeout=60)
    return AsyncOpenAI(base_url=s.gateway_base_url, api_key=s.gateway_api_key, http_client=http)


def browser_use_llm():
    """LLM handed to the browser-use Agent. Imported lazily so `app.engine` stays import-safe."""
    from browser_use import ChatOpenAI

    s = get_settings()
    # browser-use's ChatOpenAI passes http_client straight to AsyncOpenAI; use it to
    # tolerate the gateway's self-signed cert (verify=False), same as the judge client.
    http = httpx.AsyncClient(verify=s.gateway_verify_ssl, timeout=120)
    return ChatOpenAI(
        # browser-use agent can run a different (e.g. local VLM) model than the judge;
        # falls back to the shared gateway_model when AGENT_MODEL is unset.
        model=s.agent_model or s.gateway_model,
        base_url=s.gateway_base_url,
        api_key=s.gateway_api_key,
        http_client=http,
        # complex pages produce long structured output; the 4096 default truncates it
        # into invalid JSON. raise the ceiling and also put the schema in the system
        # prompt so the model reliably returns the right shape.
        max_completion_tokens=s.gateway_max_tokens,
        add_schema_to_system_prompt=True,
    )

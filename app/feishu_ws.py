"""Feishu long-connection (WebSocket) worker — no public callback URL needed.

The app dials OUT to Feishu over a persistent WebSocket; Feishu pushes events
down it. Authentication is by app_id/app_secret, so there is no verification
token or callback URL to expose — the right fit for an intranet deployment.

Run as its own process:  python -m app.feishu_ws

It reuses the exact same handler as the HTTP webhook (app.feishu.handle_message_event);
only the transport differs. Config is read from the System-settings store (env
fallback), and the worker waits until the bot is configured before connecting.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import lark_oapi as lark

from app.feishu import handle_message_event

log = logging.getLogger("testpilot.feishu.ws")

# A dedicated event loop in a background thread runs the async handler, so the
# SDK's receive loop is never blocked by DB/LLM/network work per message.
_loop = asyncio.new_event_loop()


def _start_loop() -> None:
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


def _to_payload(data) -> dict:
    """Adapt the SDK's typed event to the dict shape parse_message_event expects."""
    m = data.event.message
    sender = getattr(data.event, "sender", None)
    open_id = None
    if sender is not None and getattr(sender, "sender_id", None) is not None:
        open_id = sender.sender_id.open_id
    # SDK mentions are typed MentionEvent objects, NOT dicts — passing them
    # through crashed the parser (silently: the future's exception was never
    # read) and swallowed every @-text message. Normalize to webhook shape here.
    mentions = [
        {
            "id": {"open_id": getattr(getattr(mn, "id", None), "open_id", None)},
            "key": getattr(mn, "key", None),
            "name": getattr(mn, "name", None),
        }
        for mn in (m.mentions or [])
    ]
    return {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": open_id}},
            "message": {
                "message_id": m.message_id,
                "chat_id": m.chat_id,
                "chat_type": m.chat_type,
                "message_type": m.message_type,
                "content": m.content,
                "create_time": getattr(m, "create_time", None),
                "mentions": mentions,
            },
        },
    }


def _log_failure(fut) -> None:
    """Surface handler crashes — run_coroutine_threadsafe drops them silently."""
    exc = fut.exception()
    if exc is not None:
        log.error("feishu ws: handler crashed", exc_info=exc)


def _on_message(data) -> None:
    try:
        payload = _to_payload(data)
    except Exception:
        log.exception("feishu ws: failed to adapt event")
        return
    # Hand off to the background loop; handle_message_event owns its own error handling.
    asyncio.run_coroutine_threadsafe(handle_message_event(payload), _loop).add_done_callback(
        _log_failure
    )


def _on_card_action(data) -> None:
    """A card button was clicked (card.action.trigger)."""
    from app.feishu import handle_card_action

    try:
        event = {
            "value": getattr(data.event.action, "value", None) or {},
            "chat_id": getattr(data.event.context, "open_chat_id", None),
        }
    except Exception:
        log.exception("feishu ws: failed to adapt card action")
        return
    asyncio.run_coroutine_threadsafe(handle_card_action(event), _loop).add_done_callback(
        _log_failure
    )


async def _load_config() -> dict:
    from app.db import db_session
    from app.feishu import resolve_config

    async with db_session() as s:
        return await resolve_config(s)


def _wait_for_config(poll_s: int = 30) -> dict:
    """Block until app_id/app_secret are configured (via System settings or env)."""
    while True:
        cfg = asyncio.run(_load_config())
        if cfg["app_id"] and cfg["app_secret"]:
            return cfg
        log.warning("feishu ws: bot not configured yet — retrying in %ss", poll_s)
        time.sleep(poll_s)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = _wait_for_config()
    threading.Thread(target=_start_loop, daemon=True).start()

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message)
        .register_p2_card_action_trigger(_on_card_action)
        .build()
    )
    client = lark.ws.Client(
        cfg["app_id"],
        cfg["app_secret"],
        event_handler=handler,
        domain=cfg["api_base"],
        log_level=lark.LogLevel.INFO,
    )
    # Reliability floor: poll for missed messages on startup and every couple of
    # minutes after. The ws connection has twice died silently (connected, zero
    # events, no reconnect) — with this loop it is only a latency optimization;
    # anything the socket drops is picked up by the next poll. _SEEN dedups the
    # overlap between live delivery and the poll.
    from app.feishu import catch_up_missed

    async def _poll_forever(interval_s: int = 120) -> None:
        while True:
            await catch_up_missed()  # never raises
            await asyncio.sleep(interval_s)

    asyncio.run_coroutine_threadsafe(_poll_forever(), _loop)

    log.info("feishu ws: connecting (domain=%s)…", cfg["api_base"])
    client.start()  # blocks; auto-reconnects


if __name__ == "__main__":
    main()

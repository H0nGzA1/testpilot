"""Proactive Feishu pushes to a project's bound group chat. All best-effort —
never raise into the caller (run finalize / issue update)."""

from __future__ import annotations

import logging

from app.models import Issue, Project, Run

log = logging.getLogger("testpilot.feishu.notify")


async def _client(session):
    """A configured FeishuClient, or None when the bot isn't configured."""
    from app.feishu import FeishuClient, resolve_config

    cfg = await resolve_config(session)
    if not (cfg["app_id"] and cfg["app_secret"]):
        return None
    return FeishuClient(cfg["app_id"], cfg["app_secret"], cfg["api_base"])


async def _client_and_chat(session, project_id: int):
    """Return (FeishuClient, chat_id, project_name) if the project is bound and the
    bot is configured, else (None, None, None)."""
    proj = await session.get(Project, project_id)
    if proj is None or not proj.feishu_chat_id:
        return None, None, None
    client = await _client(session)
    if client is None:
        return None, None, None
    return client, proj.feishu_chat_id, proj.name


async def _reporter(session, issue_id: int) -> tuple[str | None, str | None]:
    """(open_id, name) of whoever reported the issue in chat, or (None, None)."""
    from sqlalchemy import select

    from app.models import FeedbackItem

    fb = (
        (await session.execute(select(FeedbackItem).where(FeedbackItem.issue_id == issue_id)))
        .scalars()
        .first()
    )
    return (fb.sender_id, fb.sender_name) if fb else (None, None)


async def mirror_issue(
    issue_id: int,
    message_id: str | None = None,
    image_keys: list[str] | None = None,
) -> None:
    """Create the Bitable defect row for an Issue if not already mirrored (best-effort).

    When the feedback message carried screenshots (message_id + image_keys), they
    are copied into the row's 问题截图 attachment field.
    """
    from app.db import db_session
    from app import feishu_bitable

    try:
        async with db_session() as s:
            issue = await s.get(Issue, issue_id)
            if issue is None or issue.bitable_record_id:
                return  # gone, or already mirrored
            proj = await s.get(Project, issue.project_id)
            if proj is None or not (proj.feishu_bitable_app_token and proj.feishu_bitable_table_id):
                return
            client = await _client(s)
            if client is None:
                return
            tokens: list[str] = []
            for i, key in enumerate(image_keys or []):
                if message_id is None:
                    break
                data = await client.download_message_resource(message_id, key)
                if data is None:
                    continue
                tok = await feishu_bitable.upload_screenshot(
                    client, proj.feishu_bitable_app_token, data, f"issue{issue_id}_{i + 1}.png"
                )
                if tok:
                    tokens.append(tok)
            rec = await feishu_bitable.create_issue_record(
                client,
                proj.feishu_bitable_app_token,
                proj.feishu_bitable_table_id,
                issue,
                proj.name,
                *await _reporter(s, issue_id),
                screenshot_tokens=tokens,
            )
            if rec:
                issue.bitable_record_id = rec
    except Exception:
        log.exception("bitable mirror_issue failed issue=%s", issue_id)


async def sync_issue_to_bitable(issue_id: int) -> None:
    """Keep the Bitable row in sync with an Issue's status (create it if missing)."""
    from app.db import db_session
    from app import feishu_bitable

    try:
        async with db_session() as s:
            issue = await s.get(Issue, issue_id)
            if issue is None:
                return
            proj = await s.get(Project, issue.project_id)
            if proj is None or not (proj.feishu_bitable_app_token and proj.feishu_bitable_table_id):
                return
            client = await _client(s)
            if client is None:
                return
            app_token, table_id = proj.feishu_bitable_app_token, proj.feishu_bitable_table_id
            if issue.bitable_record_id is None:
                rec = await feishu_bitable.create_issue_record(
                    client, app_token, table_id, issue, proj.name, *await _reporter(s, issue_id)
                )
                if rec:
                    issue.bitable_record_id = rec
                return
            record_id, status = issue.bitable_record_id, issue.status
        await feishu_bitable.update_status(client, app_token, table_id, record_id, status)
    except Exception:
        log.exception("bitable issue-status sync failed issue=%s", issue_id)


async def push_run_result(run_id: int) -> None:
    """Push a run's result card to its project's bound chat."""
    from app.db import db_session
    from app.feishu_cards import run_result_card

    try:
        async with db_session() as s:
            run = await s.get(Run, run_id)
            if run is None:
                return
            client, chat_id, project_name = await _client_and_chat(s, run.project_id)
            if client is None:
                return
            card = run_result_card(run, project_name)
        await client.send_card(chat_id, card)
    except Exception:
        log.exception("feishu push_run_result failed run=%s", run_id)


async def push_issue_update(issue_id: int) -> None:
    """Push an issue-status card to its project's bound chat."""
    from app.db import db_session
    from app.feishu_cards import issue_update_card

    try:
        async with db_session() as s:
            issue = await s.get(Issue, issue_id)
            if issue is None:
                return
            client, chat_id, project_name = await _client_and_chat(s, issue.project_id)
            if client is None:
                return
            card = issue_update_card(issue, project_name)
        await client.send_card(chat_id, card)
    except Exception:
        log.exception("feishu push_issue_update failed issue=%s", issue_id)

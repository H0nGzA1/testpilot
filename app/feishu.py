"""Feishu (Lark) feedback bot: collect problems from chat → feedback + Issue.

Flow (runs in a background task so the webhook returns 200 within Feishu's 3s
window):

  parse event → ONE LLM call {is_feedback, category, severity, title,
  project_id, should_answer, answer} → record a FeedbackItem → promote bug/
  feature items to an Issue (auto-synced to GitLab) → reply in-thread.

The project a message belongs to is auto-identified by the LLM from the list of
active projects; a message that maps to no project is still recorded but not
promoted to an Issue (there's no board to put it on).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.feishu_cards import confirm_run_card
from app.llm import llm_config, openai_client
from app.models import FeedbackItem, Issue, Project, Run, TestCase
from app.settings_store import get_setting, set_setting

log = logging.getLogger("testpilot.feishu")

_TRUE = {"1", "true", "yes", "on"}


async def resolve_config(session) -> dict:
    """Effective Feishu config: admin-managed AppSetting overrides, else env defaults.

    Lets the bot be configured from System settings (secrets encrypted at rest)
    without a redeploy, while keeping .env as the fallback.

    ENABLE_FEISHU=false returns an unconfigured config — the single choke point
    every Feishu path (notify, ws worker, webhook) already no-ops on.
    """
    s = get_settings()
    if not s.enable_feishu:
        return {
            "app_id": "",
            "app_secret": "",
            "verification_token": "",
            "api_base": s.feishu_api_base,
            "auto_answer_detected": False,
        }

    async def sv(key: str, default: str) -> str:
        v = await get_setting(session, f"feishu_{key}")
        return v if v is not None else default

    auto = await get_setting(session, "feishu_auto_answer_detected")
    return {
        "app_id": await sv("app_id", s.feishu_app_id),
        "app_secret": await sv("app_secret", s.feishu_app_secret),
        "verification_token": await sv("verification_token", s.feishu_verification_token),
        "api_base": (await sv("api_base", s.feishu_api_base)) or s.feishu_api_base,
        "auto_answer_detected": (auto.lower() in _TRUE)
        if auto is not None
        else s.feishu_auto_answer_detected,
    }


# Keep strong refs to background tasks so they aren't garbage-collected mid-run.
_TASKS: set[asyncio.Task] = set()

# High-water mark (Feishu create_time, ms) of the newest message we've handled.
# Lets the ws worker replay anything that arrived while it was down/disconnected
# — Feishu's long-connection mode does NOT redeliver missed events.
WATERMARK_KEY = "feishu_ws_watermark"

# message_ids handled by this process: dedups the catch-up replay against live ws
# delivery (and webhook retries). ponytail: wholesale clear as the cap — dedup
# only matters within the minutes-long overlap window.
_SEEN: set[str] = set()

# Categories that belong on the Issue Kanban (the rest stay feedback-only).
_PROMOTE_CATEGORIES = {"bug", "feature"}

# @_user_N is Feishu's placeholder for an @-mention; strip before recording/LLM.
_MENTION_RE = re.compile(r"@_user_\d+")

# `@bot 绑定 <项目>` / `@bot bind <project>` — bind this chat to a project.
# Allow no space after the verb (Chinese users type "绑定商城" not "绑定 商城").
_BIND_RE = re.compile(r"^\s*(?:绑定|bind)\s*(.+?)\s*$", re.IGNORECASE)


def _parse_bind_command(text: str) -> str | None:
    """Project name from a bind command, or None if the text isn't one."""
    m = _BIND_RE.match(text)
    name = m.group(1).strip() if m else ""
    return name or None


# `@bot 跑 [项目]` / `@bot 重跑` — trigger a run (a confirm card is sent first).
_RERUN_RE = re.compile(r"^\s*(?:重跑|再跑一?次?|rerun)", re.IGNORECASE)
_RUN_RE = re.compile(r"^\s*(?:跑|运行|run)\s*(.*)$", re.IGNORECASE)


def _parse_run_command(text: str) -> tuple[str, str] | None:
    """('rerun', '') or ('run', target) or None. Confirmation card is the safety net."""
    if _RERUN_RE.match(text):
        return ("rerun", "")
    m = _RUN_RE.match(text)
    if m:
        return ("run", (m.group(1) or "").strip())
    return None


# Non-@ messages must contain a problem keyword before we spend an LLM call on them
# (cheap pre-filter for ambient monitoring). @-mentions bypass this entirely.
# Broad on purpose — the LLM still filters false positives; we'd rather spend a
# cheap classify than swallow a real problem.
_PROBLEM_KEYWORDS = re.compile(
    r"报错|错误|出错|报了|报警|异常|崩|闪退|卡|慢|失败|失效|无法|不能|不了|打不开|"
    r"进不去|登不|上不去|加载|转圈|空白|白屏|超时|挂了|死机|没反应|没响应|无响应|"
    r"不显示|显示不|不对|有误|故障|问题|需求|建议|优化|求助|帮忙看|帮看|复现|重现|"
    r"挂了|坏了|不好使|用不了|点不了|bug|error|fail|crash|timeout|500|502|503|504|404",
    re.IGNORECASE,
)


def _looks_like_problem(text: str) -> bool:
    return bool(_PROBLEM_KEYWORDS.search(text))


_SYSTEM_PROMPT = (
    "你是测试团队的问题收集助手。给你一条群/私聊消息和一份项目清单,你要:\n"
    "1) 判断这条消息是否是值得记录的『问题/反馈/需求』(bug、报错、疑问、功能建议)。\n"
    "2) 从项目清单里挑出它最可能属于的项目 id(按项目名/域名匹配);无法确定填 null。\n"
    "3) 需要时给出简洁回答。\n"
    "4) 一条消息里如果列了多个彼此独立的问题(常见形式:1. 2. 3. 或分行罗列),"
    "在 items 里逐条拆开,每条一个对象;只有一个问题时 items 就只放一条。"
    "拆分时保留用户原话,不要合并、不要臆造。\n"
    "只输出一个 JSON 对象,不要多余文字,字段:\n"
    '{"is_feedback": bool, "category": "bug|question|feature|other", '
    '"severity": "low|medium|high|critical", "title": "一句话概括(<=30字)", '
    '"project_id": <int|null>, "should_answer": bool, "answer": "简洁回答,无法回答则空字符串", '
    '"items": [{"title": "该条一句话概括(<=30字)", "content": "该条用户原话", '
    '"category": "bug|question|feature|other", "severity": "low|medium|high|critical"}]}'
)


class FeishuClient:
    """Thin Feishu Open API client: tenant-token caching + in-thread text reply."""

    def __init__(self, app_id: str, app_secret: str, api_base: str) -> None:
        self._base = api_base.rstrip("/")
        self._app_id = app_id
        self._app_secret = app_secret
        self._token: str | None = None
        self._token_exp: float = 0.0

    async def _tenant_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_exp - 60:
            return self._token
        url = f"{self._base}/open-apis/auth/v3/tenant_access_token/internal"
        async with httpx.AsyncClient(timeout=10) as client:
            data = (
                await client.post(
                    url, json={"app_id": self._app_id, "app_secret": self._app_secret}
                )
            ).json()
        if data.get("code") != 0:
            raise RuntimeError(f"feishu token error: {data}")
        self._token = data["tenant_access_token"]
        self._token_exp = now + int(data.get("expire", 7200))
        return self._token

    async def reply_text(self, message_id: str, text: str) -> None:
        token = await self._tenant_token()
        url = f"{self._base}/open-apis/im/v1/messages/{message_id}/reply"
        body = {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)}
        async with httpx.AsyncClient(timeout=15) as client:
            data = (
                await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
            ).json()
        if data.get("code") != 0:
            log.warning("feishu reply failed message=%s resp=%s", message_id, data)

    async def reply_card(self, message_id: str, card: dict) -> None:
        token = await self._tenant_token()
        url = f"{self._base}/open-apis/im/v1/messages/{message_id}/reply"
        body = {"msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)}
        async with httpx.AsyncClient(timeout=15) as client:
            data = (
                await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
            ).json()
        if data.get("code") != 0:
            log.warning("feishu reply_card failed message=%s resp=%s", message_id, data)

    async def reply_markdown(self, message_id: str, md: str) -> None:
        """Reply with a card whose single element is a Markdown block (renders **bold**,
        lists, `code`, links). Feishu text messages don't render Markdown; cards do."""
        card = {
            "config": {"wide_screen_mode": True},
            "elements": [{"tag": "markdown", "content": md}],
        }
        await self.reply_card(message_id, card)

    async def send_markdown(self, chat_id: str, md: str) -> None:
        card = {
            "config": {"wide_screen_mode": True},
            "elements": [{"tag": "markdown", "content": md}],
        }
        await self.send_card(chat_id, card)

    async def send_card(self, chat_id: str, card: dict) -> None:
        token = await self._tenant_token()
        url = f"{self._base}/open-apis/im/v1/messages"
        body = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            data = (
                await client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"receive_id_type": "chat_id"},
                    json=body,
                )
            ).json()
        if data.get("code") != 0:
            log.warning("feishu send_card failed chat=%s resp=%s", chat_id, data)

    async def send_text(self, chat_id: str, text: str) -> None:
        token = await self._tenant_token()
        url = f"{self._base}/open-apis/im/v1/messages"
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            data = (
                await client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"receive_id_type": "chat_id"},
                    json=body,
                )
            ).json()
        if data.get("code") != 0:
            log.warning("feishu send_text failed chat=%s resp=%s", chat_id, data)

    async def download_message_resource(self, message_id: str, file_key: str) -> bytes | None:
        """Raw bytes of an image/file attached to a message; None on any error."""
        token = await self._tenant_token()
        url = f"{self._base}/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {token}"}, params={"type": "image"}
            )
        if resp.status_code != 200 or resp.headers.get("content-type", "").startswith(
            "application/json"
        ):
            log.warning(
                "feishu download resource failed message=%s key=%s status=%s",
                message_id,
                file_key,
                resp.status_code,
            )
            return None
        return resp.content

    async def list_recent_texts(self, chat_id: str, limit: int = 12) -> list[str]:
        """Recent text messages in a chat, oldest→newest. Best-effort context.

        Needs the app's message-history read permission; on any error returns [].
        """
        token = await self._tenant_token()
        url = f"{self._base}/open-apis/im/v1/messages"
        params = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "sort_type": "ByCreateTimeDesc",
            "page_size": limit,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            data = (
                await client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
            ).json()
        if data.get("code") != 0:
            log.warning("feishu list messages failed chat=%s resp=%s", chat_id, data)
            return []
        out: list[str] = []
        for item in (data.get("data") or {}).get("items") or []:
            if item.get("msg_type") != "text":
                continue
            try:
                txt = json.loads(item["body"]["content"]).get("text", "")
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            txt = _MENTION_RE.sub("", txt).strip()
            if txt:
                out.append(txt)
        out.reverse()  # API returns newest-first; we want oldest→newest
        return out


def _extract_post_text(content_json: str) -> str:
    """Pull all plain text out of a Feishu 富文本(post) message (screenshots + text).

    Post content is {title, content: [[{tag,text|image_key|...}, ...], ...]}. We
    keep 'text' elements (and the title), joining lines with spaces; 'at'/'img'
    elements are ignored.
    """
    try:
        data = json.loads(content_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""
    lines = [data.get("title") or ""]
    for line in data.get("content") or []:
        if not isinstance(line, list):
            continue
        lines.append("".join(el.get("text", "") for el in line if el.get("tag") == "text"))
    return " ".join(x for x in lines if x).strip()


def _post_image_keys(content_json: str) -> list[str]:
    """image_keys of screenshots embedded in a 富文本(post) message's `img` elements."""
    try:
        data = json.loads(content_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return []
    return [
        key
        for line in (data.get("content") or [])
        if isinstance(line, list)
        for el in line
        if isinstance(el, dict) and el.get("tag") == "img" and (key := el.get("image_key"))
    ]


def _post_at_ids(content_json: str) -> list[str]:
    """open_ids of users @-mentioned inside a 富文本(post) message's `at` elements."""
    try:
        data = json.loads(content_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return []
    ids: list[str] = []
    for line in data.get("content") or []:
        if not isinstance(line, list):
            continue
        for el in line:
            if el.get("tag") == "at":
                oid = el.get("user_id") or el.get("open_id")
                if oid:
                    ids.append(oid)
    return ids


# The bot's own (open_id, app_name), resolved once, so we can tell "@bot" from
# "@someone-else" — whether the @ is a real at-element or just literal "@Name" text.
_bot_info_cache: tuple[str | None, str | None] | None = None


async def _bot_info(client) -> tuple[str | None, str | None]:
    global _bot_info_cache
    if _bot_info_cache is not None:
        return _bot_info_cache
    open_id = name = None
    try:
        token = await client._tenant_token()
        url = f"{client._base}/open-apis/bot/v3/info"
        async with httpx.AsyncClient(timeout=10) as h:
            data = (await h.get(url, headers={"Authorization": f"Bearer {token}"})).json()
        bot = data.get("bot") or {}
        open_id, name = bot.get("open_id"), bot.get("app_name")
        _bot_info_cache = (open_id, name)
    except Exception:
        log.exception("feishu: resolve bot info failed")
    return open_id, name


# open_id -> display name. Names rarely change; a process restart refreshes.
_NAME_CACHE: dict[str, str] = {}


async def user_name(client, open_id: str | None, chat_id: str | None = None) -> str | None:
    """Display name behind an open_id — best-effort, cached.

    Tries the contact API (needs contact:user.base:readonly); falls back to the
    chat's member list (im:chat:readonly) so one missing scope isn't fatal.
    """
    if client is None or not open_id:
        return None
    if open_id in _NAME_CACHE:
        return _NAME_CACHE[open_id]
    name = None
    try:
        headers = {"Authorization": f"Bearer {await client._tenant_token()}"}
        async with httpx.AsyncClient(timeout=10) as h:
            url = f"{client._base}/open-apis/contact/v3/users/{open_id}?user_id_type=open_id"
            data = (await h.get(url, headers=headers)).json()
            if data.get("code") == 0:
                name = ((data.get("data") or {}).get("user") or {}).get("name")
            elif chat_id:
                # ponytail: first page only — chats with >100 members fall back to open_id
                url = (
                    f"{client._base}/open-apis/im/v1/chats/{chat_id}/members"
                    "?member_id_type=open_id&page_size=100"
                )
                data = (await h.get(url, headers=headers)).json()
                name = next(
                    (
                        m.get("name")
                        for m in ((data.get("data") or {}).get("items") or [])
                        if m.get("member_id") == open_id
                    ),
                    None,
                )
    except Exception:
        log.exception("feishu: resolve user name failed open_id=%s", open_id)
    if name:
        _NAME_CACHE[open_id] = name
    else:
        log.warning(
            "feishu: no display name for %s — grant contact:user.base:readonly or im:chat:readonly",
            open_id,
        )
    return name


def parse_message_event(payload: dict) -> dict | None:
    """Extract text from an im.message.receive_v1 payload (plain text or 富文本/post).

    Returns {message_id, chat_id, chat_type, sender_id, text, mentioned} or None
    for messages with no usable text (image-only, sticker, file, …).
    """
    event = payload.get("event") or {}
    message = event.get("message") or {}
    msg_type = message.get("message_type")
    message_id = message.get("message_id")
    chat_id = message.get("chat_id")
    if not message_id or not chat_id:
        return None
    if msg_type == "text":
        try:
            raw = json.loads(message.get("content") or "{}").get("text", "")
        except (json.JSONDecodeError, AttributeError):
            raw = ""
    elif msg_type == "post":
        raw = _extract_post_text(message.get("content") or "{}")
    else:
        return None  # image-only / sticker / file — no text to act on
    text = _MENTION_RE.sub("", raw).strip()
    chat_type = message.get("chat_type") or "group"
    sender_id = ((event.get("sender") or {}).get("sender_id") or {}).get("open_id")
    # Collect open_ids of everyone @-mentioned. Text messages carry them in
    # message.mentions; 富文本(post) carries them as `at` elements in the content.
    mention_ids = [
        oid for m in (message.get("mentions") or []) if (oid := (m.get("id") or {}).get("open_id"))
    ]
    if msg_type == "post":
        mention_ids += _post_at_ids(message.get("content") or "{}")
    # Provisional: p2p or anyone mentioned. handle_message_event narrows this to
    # "the BOT was mentioned" once it can resolve the bot's own open_id.
    mentioned = chat_type == "p2p" or bool(mention_ids) or bool(message.get("mentions"))
    return {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "sender_id": sender_id,
        "text": text,
        "mentioned": mentioned,
        "mention_ids": mention_ids,
        "create_time": message.get("create_time"),
        "image_keys": _post_image_keys(message.get("content") or "{}")
        if msg_type == "post"
        else [],
    }


def _parse_json(raw: str) -> dict | None:
    """Parse the classifier's JSON, tolerating ```json fences and surrounding prose."""
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def _bound_project(session, chat_id: str):
    """The Project explicitly bound to this Feishu chat, or None."""
    if not chat_id:
        return None
    return (
        (await session.execute(select(Project).where(Project.feishu_chat_id == chat_id)))
        .scalars()
        .first()
    )


async def _recent_context(client: FeishuClient | None, chat_id: str) -> str:
    """Best-effort recent chat transcript (oldest→newest) for LLM context."""
    if client is None:
        return ""
    try:
        texts = await client.list_recent_texts(chat_id)
    except Exception:
        log.exception("feishu: fetch context failed chat=%s", chat_id)
        return ""
    return "\n".join(texts[-12:])


async def _classify(
    text: str,
    projects: list[dict],
    context: str = "",
    bound_project_id: int | None = None,
) -> dict | None:
    """One LLM round-trip: classify + pick a project + optional answer.

    When ``bound_project_id`` is set the project is fixed (no guessing). ``context``
    is the recent chat transcript, so short messages ("下单报错") are judged in context.
    """
    if bound_project_id is not None:
        project_hint = (
            f"本消息所属项目已确定为 id={bound_project_id};project_id 直接填 {bound_project_id}。"
        )
    else:
        project_lines = (
            "\n".join(
                f"- id={p['id']} name={p['name']} url={p.get('base_url') or ''}" for p in projects
            )
            or "(无项目)"
        )
        project_hint = f"项目清单:\n{project_lines}"
    ctx = f"\n\n【群里最近对话,供理解上下文,最后一条即本条】\n{context}" if context else ""
    client = await openai_client()
    resp = await client.chat.completions.create(
        model=(await llm_config()).model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{project_hint}{ctx}\n\n【需要判断的消息】\n{text}"},
        ],
    )
    return _parse_json(resp.choices[0].message.content or "")


def _feedback_items(result: dict, text: str) -> list[dict]:
    """The distinct problems in one message: the model's split, else the whole message.

    A "1. … 2. … 3. …" laundry list becomes one record per line so each can be
    tracked (and closed) on its own.
    """
    out: list[dict] = []
    for it in result.get("items") or []:
        if not isinstance(it, dict):
            continue
        content = (it.get("content") or it.get("title") or "").strip()
        if not content:
            continue
        out.append(
            {
                "title": (it.get("title") or content)[:60],
                "content": content,
                "category": it.get("category") or result.get("category") or "other",
                "severity": it.get("severity") or result.get("severity") or "medium",
            }
        )
    if not out:
        out = [
            {
                "title": result.get("title") or text[:30],
                "content": text,
                "category": result.get("category") or "other",
                "severity": result.get("severity") or "medium",
            }
        ]
    return out


async def _advance_watermark(create_time: str | None) -> None:
    """Persist the newest handled create_time (ms). Best-effort — never raises."""
    from app.db import db_session

    try:
        new = int(create_time or 0)
    except (TypeError, ValueError):
        return
    if not new:
        return
    try:
        async with db_session() as s:
            cur = await get_setting(s, WATERMARK_KEY)
            if new > int(cur or 0):
                await set_setting(s, WATERMARK_KEY, str(new))
    except Exception:
        log.exception("feishu: watermark update failed")


def _api_item_to_payload(item: dict) -> dict:
    """Adapt a GET /im/v1/messages item to the receive_v1 event payload shape."""
    mentions = [
        {
            "id": {
                "open_id": (m.get("id") or {}).get("open_id")
                if isinstance(m.get("id"), dict)
                else m.get("id")
            },
            "key": m.get("key"),
            "name": m.get("name"),
        }
        for m in (item.get("mentions") or [])
    ]
    return {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": (item.get("sender") or {}).get("id")}},
            "message": {
                "message_id": item.get("message_id"),
                "chat_id": item.get("chat_id"),
                "chat_type": "group",  # only bound (group) chats are caught up
                "message_type": item.get("msg_type"),
                "content": (item.get("body") or {}).get("content"),
                "create_time": item.get("create_time"),
                "mentions": mentions,
            },
        },
    }


async def _fetch_since(client: FeishuClient, chat_id: str, since_ms: int) -> list[dict]:
    """User messages in a chat newer than since_ms, oldest→newest. Raises on API error."""
    token = await client._tenant_token()
    url = f"{client._base}/open-apis/im/v1/messages"
    params: dict = {
        "container_id_type": "chat",
        "container_id": chat_id,
        "sort_type": "ByCreateTimeAsc",
        "start_time": since_ms // 1000,  # API takes seconds; ms filter below is exact
        "page_size": 50,
    }
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=10) as http:
        for _ in range(5):  # ponytail: 250 msgs per chat per catch-up is plenty
            resp = (
                await http.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
            ).json()
            if resp.get("code") != 0:
                raise RuntimeError(f"list messages failed: {resp}")
            data = resp.get("data") or {}
            for item in data.get("items") or []:
                if (item.get("sender") or {}).get("sender_type") != "user":
                    continue  # our own replies etc.
                if int(item.get("create_time") or 0) <= since_ms:
                    continue
                out.append(item)
            if not data.get("has_more"):
                break
            params["page_token"] = data.get("page_token")
    return out


async def catch_up_missed() -> None:
    """Replay bound-chat messages that arrived while no ws connection was up.

    Feishu's long-connection mode drops events pushed while disconnected (deploy
    restarts, silent ws death). On startup we pull each bound chat's history past
    the watermark and feed it through handle_message_event; _SEEN dedups against
    messages the live connection delivers concurrently. Never raises.
    """
    from app.db import db_session

    try:
        async with db_session() as s:
            cfg = await resolve_config(s)
            if not (cfg["app_id"] and cfg["app_secret"]):
                return
            chats = {
                p.feishu_chat_id
                for p in (await s.execute(select(Project))).scalars()
                if p.feishu_chat_id
            }
            cur = await get_setting(s, WATERMARK_KEY)
            if cur is None:
                # First run: start the watermark now, don't replay old history.
                await set_setting(s, WATERMARK_KEY, str(int(time.time() * 1000)))
                return
        since_ms = max(int(cur), int(time.time() * 1000) - 24 * 3600 * 1000)
        client = FeishuClient(cfg["app_id"], cfg["app_secret"], cfg["api_base"])
        for chat_id in chats:
            try:
                items = await _fetch_since(client, chat_id, since_ms)
            except Exception:
                log.exception("feishu catch-up: fetch failed chat=%s", chat_id)
                continue
            fresh = [it for it in items if (it.get("message_id") or "") not in _SEEN]
            if fresh:
                log.info(
                    "feishu catch-up: replaying %d missed message(s) chat=%s", len(fresh), chat_id
                )
            for item in fresh:
                try:
                    await handle_message_event(_api_item_to_payload(item))
                except Exception:
                    log.exception(
                        "feishu catch-up: replay failed message=%s", item.get("message_id")
                    )
    except Exception:
        log.exception("feishu catch-up failed")


def schedule(payload: dict) -> None:
    """Fire-and-forget entry point called by the webhook."""
    task = asyncio.create_task(handle_message_event(payload))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def handle_message_event(payload: dict) -> None:
    """Background worker: classify one message, record it, promote + reply."""
    msg = (payload.get("event") or {}).get("message") or {}
    mid = msg.get("message_id")
    if mid and mid in _SEEN:
        return
    evt = parse_message_event(payload)
    if evt is None:
        log.info("recv unsupported message_type=%s (skipped, no text)", msg.get("message_type"))
        # Still advance: otherwise an image-only tail keeps being refetched.
        await _advance_watermark(msg.get("create_time"))
        return
    # Mark seen only after a successful parse — if anything above throws, the
    # catch-up poll can still rescue the message on its next cycle.
    if mid:
        _SEEN.add(mid)
        if len(_SEEN) > 2000:
            _SEEN.clear()
    # Scan trail: every message we act on leaves a line so nothing is invisible.
    log.info(
        "recv chat=%s mentioned=%s text=%r",
        evt["chat_id"],
        evt["mentioned"],
        (evt["text"] or "")[:60],
    )
    # Advance before processing: a crash mid-classify loses one message (rare)
    # instead of re-replying to everything since it on the next restart.
    await _advance_watermark(evt.get("create_time"))
    if not evt["text"]:
        return

    from app.celery_app import enqueue_push
    from app.db import db_session

    reply: str = ""
    reply_card_payload: dict | None = None
    promoted_issue_ids: list[int] = []
    cfg: dict = {}
    client: FeishuClient | None = None
    try:
        async with db_session() as s:
            cfg = await resolve_config(s)
            if cfg["app_id"] and cfg["app_secret"]:
                client = FeishuClient(cfg["app_id"], cfg["app_secret"], cfg["api_base"])

            # Narrow "mentioned" to "the BOT was @-mentioned". The @ may be a real
            # at-element (→ mention_ids) or just literal "@Name" text (post messages
            # sometimes send it that way); match either. Also stops reacting to
            # @-someone-else.
            if client is not None:
                bot_id, bot_name = await _bot_info(client)
                if bot_id or bot_name:
                    by_id = bool(bot_id) and bot_id in evt["mention_ids"]
                    by_name = bool(bot_name) and f"@{bot_name}" in (evt["text"] or "")
                    evt["mentioned"] = evt["chat_type"] == "p2p" or by_id or by_name

            # Ambient cost gate: a non-@ message must look like a problem before we
            # spend LLM on it. Flip FEISHU_AMBIENT_REQUIRE_KEYWORD=false to never drop.
            if (
                not evt["mentioned"]
                and get_settings().feishu_ambient_require_keyword
                and not _looks_like_problem(evt["text"])
            ):
                log.info("skip (no problem keyword): %r", evt["text"][:60])
                return

            bound = await _bound_project(s, evt["chat_id"])
            rows = list((await s.execute(select(Project))).scalars().all())
            projects = [{"id": p.id, "name": p.name, "base_url": p.base_url} for p in rows]

            # `@bot 绑定 <项目>` — bind this chat to a project (powers routing + push).
            bind_name = _parse_bind_command(evt["text"]) if evt["mentioned"] else None
            run_cmd = _parse_run_command(evt["text"]) if evt["mentioned"] else None
            if bind_name is not None:
                match = next((p for p in rows if p.name.lower() == bind_name.lower()), None)
                if match is not None:
                    match.feishu_chat_id = evt["chat_id"]
                    reply = (
                        f"已把本群绑定到项目「{match.name}」✅ 之后这里的问题/运行都归到该项目。"
                    )
                else:
                    names = ", ".join(p["name"] for p in projects) or "(无)"
                    reply = f"没找到项目「{bind_name}」。现有项目:{names}"
            elif run_cmd is not None:
                # Resolve target project, then send a CONFIRM card (never run directly).
                kind, target = run_cmd
                proj = bound
                if proj is None and target:
                    proj = next((p for p in rows if p.name.lower() == target.lower()), None)
                if proj is None:
                    reply = "没识别到项目。先在群里「@机器人 绑定 <项目>」,或写明项目名(如「跑 Demo-test」)。"
                else:
                    rerun_of = None
                    if kind == "rerun":
                        last = (
                            (
                                await s.execute(
                                    select(Run)
                                    .where(Run.project_id == proj.id)
                                    .order_by(Run.id.desc())
                                    .limit(1)
                                )
                            )
                            .scalars()
                            .first()
                        )
                        if last is None:
                            reply = f"「{proj.name}」还没有可重跑的运行。"
                        else:
                            rerun_of = last.id
                    if not reply:
                        count = (
                            await s.execute(
                                select(func.count())
                                .select_from(TestCase)
                                .where(
                                    TestCase.project_id == proj.id,
                                    TestCase.enabled == True,  # noqa: E712
                                )
                            )
                        ).scalar_one()
                        reply_card_payload = confirm_run_card(proj.id, proj.name, count, rerun_of)
            else:
                context = await _recent_context(client, evt["chat_id"])
                try:
                    result = await _classify(
                        evt["text"],
                        projects,
                        context=context,
                        bound_project_id=(bound.id if bound else None),
                    )
                except Exception:
                    log.exception("feishu classify failed")
                    return
                if result is None:
                    log.warning("feishu classify parse failed message=%s", evt["message_id"])
                    return
                if not result.get("is_feedback") and not evt["mentioned"]:
                    return  # not worth recording and nobody asked the bot directly

                answer = (result.get("answer") or "").strip()
                should_answer = evt["mentioned"] or (
                    cfg["auto_answer_detected"] and bool(result.get("should_answer"))
                )
                # Bound chat wins; otherwise trust the LLM's pick if it's a real project.
                if bound is not None:
                    project_id = bound.id
                else:
                    valid_ids = {p["id"] for p in projects}
                    pid = result.get("project_id")
                    project_id = pid if pid in valid_ids else None

                if not result.get("is_feedback"):
                    # @mentioned but not a problem report → grounded answer via a
                    # tool-using agent turn (queries real data / drafts a case).
                    from app.feishu_agent import agent_reply

                    try:
                        reply = await agent_reply(s, evt["text"], context, project_id)
                    except Exception:
                        log.exception("feishu agent_reply failed")
                        reply = answer if should_answer else ""
                else:
                    sender = await user_name(client, evt["sender_id"], evt["chat_id"])
                    # A "1. … 2. … 3. …" message becomes one record per problem; the
                    # first keeps the raw message_id so a Feishu retry still dedupes.
                    for n, part in enumerate(_feedback_items(result, evt["text"])):
                        item = FeedbackItem(
                            feishu_message_id=evt["message_id"]
                            if n == 0
                            else f"{evt['message_id']}#{n + 1}",
                            chat_id=evt["chat_id"],
                            chat_type=evt["chat_type"],
                            sender_id=evt["sender_id"],
                            sender_name=sender,
                            content=part["content"],
                            title=part["title"][:30],
                            category=part["category"],
                            severity=part["severity"],
                            answer=answer if (should_answer and n == 0) else None,
                            answered=bool(should_answer and answer and n == 0),
                            project_id=project_id,
                        )
                        s.add(item)
                        try:
                            await s.flush()
                        except IntegrityError:
                            # Duplicate message_id — Feishu retried; already handled.
                            await s.rollback()
                            return

                        if part["category"] in _PROMOTE_CATEGORIES and project_id is not None:
                            issue = Issue(
                                project_id=project_id,
                                title=item.title or part["content"][:60],
                                description=part["content"],
                                severity=part["severity"],
                                labels=["feishu"],
                                created_by=evt["sender_id"],
                            )
                            s.add(issue)
                            await s.flush()
                            item.issue_id = issue.id
                            promoted_issue_ids.append(issue.id)
                            enqueue_push(issue.id)  # no-op when GitLab sync disabled

                    reply = _confirmation(promoted_issue_ids, project_id, answer)
    except Exception:
        log.exception("feishu handle_message_event failed message=%s", evt["message_id"])
        return

    # Mirror the promoted Issue into the project's Bitable defect table (best-effort),
    # carrying the reporter so the 报告人 field shows who raised it.
    if promoted_issue_ids:
        from app import feishu_notify

        for n, iid in enumerate(promoted_issue_ids):
            # Screenshots ride on the first row only — they belong to the message as
            # a whole and can't be mapped to a specific line.
            await feishu_notify.mirror_issue(
                iid,
                message_id=evt["message_id"],
                image_keys=(evt.get("image_keys") or []) if n == 0 else [],
            )

    if client is not None:
        try:
            if reply_card_payload is not None:
                await client.reply_card(evt["message_id"], reply_card_payload)
            elif reply:
                await client.reply_markdown(evt["message_id"], reply)
        except Exception:
            log.exception("feishu reply failed message=%s", evt["message_id"])


async def handle_card_action(event: dict) -> None:
    """Dispatch a button click. ``event`` = {value, chat_id}."""
    value = event.get("value") or {}
    chat_id = event.get("chat_id")
    act = value.get("act")
    if not chat_id or act not in ("run_confirm", "run_cancel"):
        return

    from app.db import db_session

    async with db_session() as s:
        cfg = await resolve_config(s)
    if not (cfg["app_id"] and cfg["app_secret"]):
        return
    client = FeishuClient(cfg["app_id"], cfg["app_secret"], cfg["api_base"])

    if act == "run_cancel":
        await client.send_text(chat_id, "已取消运行。")
        return

    run_id = await _start_run(int(value["project_id"]), value.get("rerun_of"))
    if run_id is None:
        await client.send_text(chat_id, "没有可运行的启用用例。")
        return
    await client.send_text(chat_id, f"已开始运行 run #{run_id},跑完我在这里播报结果。")


async def _start_run(project_id: int, rerun_of: int | None) -> int | None:
    """Create a Run (all enabled cases, or the rerun's case set) and launch it."""
    from app.db import db_session

    async with db_session() as s:
        if rerun_of is not None:
            src = await s.get(Run, rerun_of)
            case_ids = list(src.case_ids or []) if src else []
            name = f"重跑 #{rerun_of}"
        else:
            case_ids = [
                c.id
                for c in (
                    await s.execute(
                        select(TestCase).where(
                            TestCase.project_id == project_id,
                            TestCase.enabled == True,  # noqa: E712
                        )
                    )
                )
                .scalars()
                .all()
            ]
            name = "飞书触发运行"
        if not case_ids:
            return None
        proj = await s.get(Project, project_id)
        run = Run(
            project_id=project_id,
            name=name,
            case_ids=case_ids,
            concurrency=(proj.run_concurrency or 2) if proj else 2,
            total_count=len(case_ids),
            trigger="feishu",
        )
        s.add(run)
        await s.flush()
        run_id = run.id

    from app.api import _launch

    await _launch(run_id)
    return run_id


def _confirmation(issue_ids: list[int], project_id: int | None, answer: str) -> str:
    """Compose the in-thread confirmation the bot replies with."""
    if len(issue_ids) > 1:
        nums = "、".join(f"#{i}" for i in issue_ids)
        head = f"已拆成 {len(issue_ids)} 条并建为问题 {nums}(项目 {project_id})✅"
    elif issue_ids:
        head = f"已记录并建为问题 #{issue_ids[0]}(项目 {project_id})✅"
    elif project_id is None:
        head = "已记录 ✅(未能识别所属项目,暂未建为看板问题)"
    else:
        head = "已记录 ✅"
    return f"{head}\n\n{answer}".rstrip() if answer else head

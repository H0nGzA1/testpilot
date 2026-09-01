"""Pure-logic checks for the Feishu bot: event parsing, JSON tolerance, reply text.

No network, no DB, no LLM — just the functions with tricky logic.
"""

from __future__ import annotations

import json

from app.feishu import (
    _confirmation,
    _parse_bind_command,
    _parse_json,
    _parse_run_command,
    parse_message_event,
)
from app.feishu_cards import confirm_run_card, run_result_card


def _text_event(text: str, chat_type: str = "group", mentions=None) -> dict:
    return {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_123"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "chat_type": chat_type,
                "message_type": "text",
                "content": json.dumps({"text": text}),
                "mentions": mentions or [],
            },
        },
    }


def test_parse_strips_mention_and_flags_mentioned() -> None:
    evt = parse_message_event(_text_event("@_user_1 登录页报错了", mentions=[{"key": "@_user_1"}]))
    assert evt is not None
    assert evt["text"] == "登录页报错了"
    assert evt["mentioned"] is True
    assert evt["sender_id"] == "ou_123"


def test_parse_p2p_mentioned_and_non_text_skipped() -> None:
    assert parse_message_event(_text_event("hi", chat_type="p2p"))["mentioned"] is True
    payload = _text_event("x")
    payload["event"]["message"]["message_type"] = "image"
    assert parse_message_event(payload) is None


def test_parse_post_message_with_screenshot() -> None:
    # 富文本(post): text + image, @-mentioned — the QA-bug-report shape.
    post_content = json.dumps(
        {
            "title": "",
            "content": [
                [{"tag": "at", "user_id": "ou_bot"}, {"tag": "text", "text": "下载文件名是随机码"}],
                [{"tag": "img", "image_key": "img_x"}, {"tag": "text", "text": "需修正"}],
            ],
        }
    )
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_p",
                "chat_id": "oc_1",
                "chat_type": "group",
                "message_type": "post",
                "content": post_content,
                "mentions": [],  # post carries the @ in content, not here
            },
        },
    }
    evt = parse_message_event(payload)
    assert evt is not None
    assert "下载文件名是随机码" in evt["text"]
    assert "需修正" in evt["text"]
    # @ lives in the post's `at` element → mention_ids picks it up
    assert evt["mention_ids"] == ["ou_bot"]
    assert evt["mentioned"] is True


def test_parse_json_tolerates_fence_and_prose() -> None:
    raw = '好的\n```json\n{"is_feedback": true, "category": "bug", "project_id": 3}\n```'
    parsed = _parse_json(raw)
    assert parsed["is_feedback"] is True
    assert parsed["project_id"] == 3
    assert _parse_json("not json") is None


def test_parse_bind_command() -> None:
    assert _parse_bind_command("绑定 Demo-test") == "Demo-test"
    assert _parse_bind_command("绑定商城项目") == "商城项目"  # no space (common in Chinese)
    assert _parse_bind_command("bind smoke") == "smoke"
    assert _parse_bind_command("下单报错") is None
    assert _parse_bind_command("绑定") is None  # needs a project name


def test_looks_like_problem() -> None:
    from app.feishu import _looks_like_problem

    assert _looks_like_problem("登录页又报错了")
    assert _looks_like_problem("这个功能有个 bug")
    assert _looks_like_problem("系统崩了")
    assert _looks_like_problem("点了没反应")
    assert _looks_like_problem("报了个错")
    assert _looks_like_problem("页面打不开")
    assert not _looks_like_problem("大家早上好")
    assert not _looks_like_problem("这个不错")
    assert not _looks_like_problem("今天下午开会")


def test_parse_run_command() -> None:
    assert _parse_run_command("跑冒烟") == ("run", "冒烟")
    assert _parse_run_command("运行 Demo-test") == ("run", "Demo-test")
    assert _parse_run_command("重跑") == ("rerun", "")
    assert _parse_run_command("下单报错") is None
    assert _parse_run_command("最近跑得怎么样") is None


def test_confirm_run_card_has_buttons() -> None:
    card = confirm_run_card(2, "Demo-test", 12, None)
    actions = card["elements"][-1]["actions"]
    values = [a["value"]["act"] for a in actions]
    assert values == ["run_confirm", "run_cancel"]
    assert actions[0]["value"]["project_id"] == 2


class _Run:
    id = 7
    project_id = 2
    name = "冒烟"
    status = "completed"
    passed_count = 10
    total_count = 12


def test_run_result_card_renders() -> None:
    card = run_result_card(_Run(), "Demo-test")
    assert "测试运行完成" in card["header"]["title"]["content"]
    assert card["header"]["template"] == "red"  # 10/12 → not all passed


def test_parse_bitable_url() -> None:
    from app.feishu_bitable import parse_bitable_url

    app, tbl = parse_bitable_url(
        "https://x.feishu.cn/base/T55fb4ziRaJJDhsUXiVcoNsknke?a=1&table=tbldrYrsiMHAeXuz&view=v"
    )
    assert app == "T55fb4ziRaJJDhsUXiVcoNsknke"
    assert tbl == "tbldrYrsiMHAeXuz"
    assert parse_bitable_url("") == (None, None)
    assert parse_bitable_url("not a url") == (None, None)


def test_confirmation_variants() -> None:
    assert _confirmation([7], 3, "").startswith("已记录并建为问题 #7")
    assert _confirmation([7, 8], 3, "").startswith("已拆成 2 条并建为问题 #7、#8")
    assert "未能识别所属项目" in _confirmation([], None, "")
    assert _confirmation([], 3, "答案") == "已记录 ✅\n\n答案"


def test_api_item_roundtrips_through_parser() -> None:
    """Catch-up replay: a GET /im/v1/messages item must parse like a live event."""
    from app.feishu import _api_item_to_payload

    item = {
        "message_id": "om_9",
        "chat_id": "oc_1",
        "msg_type": "text",
        "create_time": "1787045949000",
        "sender": {"id": "ou_wang", "sender_type": "user"},
        "body": {"content": json.dumps({"text": "@_user_1 登录页报错了"})},
        "mentions": [{"id": "ou_bot", "key": "@_user_1", "name": "TestPolit"}],
    }
    evt = parse_message_event(_api_item_to_payload(item))
    assert evt is not None
    assert evt["message_id"] == "om_9"
    assert evt["text"] == "登录页报错了"
    assert evt["mentioned"] is True
    assert evt["mention_ids"] == ["ou_bot"]
    assert evt["create_time"] == "1787045949000"
    assert evt["sender_id"] == "ou_wang"


def test_ws_sdk_event_roundtrips_through_parser() -> None:
    """SDK MentionEvent objects (no .get) must be normalized before parsing —
    passing them through raw crashed the parser and swallowed @-text messages."""
    from types import SimpleNamespace as NS

    from app.feishu_ws import _to_payload

    data = NS(
        event=NS(
            sender=NS(sender_id=NS(open_id="ou_alice")),
            message=NS(
                message_id="om_ws1",
                chat_id="oc_1",
                chat_type="group",
                message_type="text",
                content=json.dumps({"text": "@_user_1 现在有哪些问题了"}),
                create_time="1787108200000",
                mentions=[NS(id=NS(open_id="ou_bot"), key="@_user_1", name="TestPolit")],
            ),
        )
    )
    evt = parse_message_event(_to_payload(data))
    assert evt is not None
    assert evt["text"] == "现在有哪些问题了"
    assert evt["mention_ids"] == ["ou_bot"]
    assert evt["mentioned"] is True
    assert evt["create_time"] == "1787108200000"


def test_bitable_fields_keep_user_words_authoritative() -> None:
    """缺陷描述 = user's original text + model summary; 问题备注 = metadata only."""
    from types import SimpleNamespace as NS

    from app.feishu_bitable import _issue_fields

    issue = NS(
        id=10,
        status="open",
        title="Agent图表重复生成两次",
        description="agent对话生成图表会出现两次，仅保留第一次出现有中文标题的图标即可。",
        severity="medium",
        labels=["feishu"],
        gitlab_iid=None,
        run_id=None,
        created_at=None,
    )
    fields = _issue_fields(issue, "demo-app")
    assert fields["缺陷描述"].startswith("agent对话生成图表会出现两次")
    assert fields["缺陷描述"].endswith("摘要：Agent图表重复生成两次")
    assert "生成图表" not in fields["问题备注"]  # user words not duplicated into 备注
    assert fields["问题备注"] == "项目：demo-app · 来源：飞书群反馈 · Issue #10"
    assert fields["缺陷来源"] == "飞书群反馈"  # no reporter resolved → category
    # no description → title alone
    issue2 = NS(**{**issue.__dict__, "description": ""})
    assert _issue_fields(issue2, "demo-app")["缺陷描述"] == "Agent图表重复生成两次"
    # reporter's name takes over 缺陷来源; category still readable in 问题备注
    with_reporter = _issue_fields(issue, "demo-app", "ou_x", "张三")
    assert with_reporter["缺陷来源"] == "张三"
    assert "来源：飞书群反馈" in with_reporter["问题备注"]
    assert with_reporter["报告人"] == [{"id": "ou_x"}]


def test_post_message_collects_image_keys() -> None:
    from app.feishu import _post_image_keys

    content = json.dumps(
        {
            "title": "",
            "content": [
                [{"tag": "text", "text": "图表重复生成"}, {"tag": "img", "image_key": "img_k1"}],
                [{"tag": "img", "image_key": "img_k2"}, {"tag": "at", "user_id": "ou_bot"}],
            ],
        }
    )
    assert _post_image_keys(content) == ["img_k1", "img_k2"]
    assert _post_image_keys("not json") == []

    evt = parse_message_event(
        {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_1"}},
                "message": {
                    "message_id": "om_p1",
                    "chat_id": "oc_1",
                    "chat_type": "group",
                    "message_type": "post",
                    "content": content,
                },
            },
        }
    )
    assert evt is not None
    assert evt["image_keys"] == ["img_k1", "img_k2"]


def test_multi_problem_message_splits_into_items() -> None:
    """A 1./2./3. laundry list becomes one record per problem; single stays single."""
    from app.feishu import _feedback_items

    result = {
        "category": "bug",
        "severity": "medium",
        "title": "Agent 0824优化",
        "items": [
            {
                "title": "sbs结果缓存",
                "content": "1.sbs结果缓存，iframe不能刷新丢失",
                "severity": "high",
            },
            {
                "title": "去掉需关注tab",
                "content": "2.自动化任务，”需关注“tab页不明确",
                "category": "feature",
            },
        ],
    }
    parts = _feedback_items(result, "原始整条消息")
    assert [p["title"] for p in parts] == ["sbs结果缓存", "去掉需关注tab"]
    assert parts[0]["severity"] == "high"  # per-item wins
    assert parts[0]["category"] == "bug"  # falls back to the message-level value
    assert parts[1]["category"] == "feature"

    # no/blank items → the whole message, one record (old behaviour)
    single = _feedback_items({"title": "标题", "category": "bug", "items": []}, "只有一个问题")
    assert len(single) == 1
    assert single[0]["content"] == "只有一个问题"
    assert single[0]["severity"] == "medium"
    assert _feedback_items({}, "裸文本")[0]["title"] == "裸文本"

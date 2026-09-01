"""Feishu interactive card builders (pure functions → card dicts).

Button ``value`` dicts are echoed back to us in the card.action.trigger event, so
we route on ``act``.
"""

from __future__ import annotations

from app.config import get_settings


def _run_web_url(project_id: int, run_id: int) -> str | None:
    base = (get_settings().public_base_url or "").rstrip("/")
    return f"{base}/projects/{project_id}/runs/{run_id}" if base else None


def confirm_run_card(
    project_id: int, project_name: str, case_count: int, rerun_of: int | None
) -> dict:
    """A [确认运行][取消] card sent before actually launching a run."""
    what = (
        f"重跑 run #{rerun_of}"
        if rerun_of
        else f"运行 **{project_name}** 的 {case_count} 个启用用例"
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "确认运行测试"},
            "template": "orange",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"要{what}吗?"}},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认运行"},
                        "type": "primary",
                        "value": {
                            "act": "run_confirm",
                            "project_id": project_id,
                            "rerun_of": rerun_of,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "取消"},
                        "type": "default",
                        "value": {"act": "run_cancel"},
                    },
                ],
            },
        ],
    }


def run_result_card(run, project_name: str) -> dict:
    """Result summary pushed when a run finishes."""
    passed = run.passed_count or 0
    total = run.total_count or 0
    ok = run.status == "completed" and passed == total and total > 0
    template = "green" if ok else ("red" if run.status != "cancelled" else "grey")
    icon = "✅" if ok else ("❌" if run.status != "cancelled" else "⚪")
    lines = [
        f"**项目**:{project_name}",
        f"**运行**:{run.name} (#{run.id})",
        f"**结果**:{passed}/{total} 通过 · 状态 {run.status}",
    ]
    elements: list = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}]
    url = _run_web_url(run.project_id, run.id)
    if url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看运行"},
                        "type": "default",
                        "url": url,
                    }
                ],
            }
        )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{icon} 测试运行完成"},
            "template": template,
        },
        "elements": elements,
    }


def issue_update_card(issue, project_name: str) -> dict:
    """Small note pushed when a bound project's issue changes status."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "问题状态更新"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{project_name}** · 问题 #{issue.id}\n"
                        f"**{issue.title}**\n"
                        f"状态 → **{issue.status}** · 严重度 {issue.severity}"
                    ),
                },
            }
        ],
    }

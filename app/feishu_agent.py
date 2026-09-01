"""Feishu bot agent turn: answer @-mentions with REAL data via read-only tools,
and create test-case drafts.

Used when a @-mention isn't a problem report (those go straight to Feedback/Issue).
The model may call tools to query runs/issues/cases or draft a case, then answers
grounded in real data instead of guessing. Running tests / rerunning needs a
confirmation card — added in Phase 3, not exposed here.

Degrades gracefully: if the gateway doesn't support function-calling, we retry
once without tools and just answer.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select

from app.llm import llm_config, openai_client
from app.models import Issue, Run, TestCase

log = logging.getLogger("testpilot.feishu.agent")

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_recent_runs",
            "description": "最近的测试运行(状态/通过率/完成时间)",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "条数,默认5"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_open_issues",
            "description": "项目的问题列表(默认未关闭)",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "open/fixed/... 留空=未关闭"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_cases",
            "description": "用例数量(启用/总)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_case_draft",
            "description": "新建一个测试用例草稿(draft 状态,待人工确认启用)",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "prompt": {
                        "type": "string",
                        "description": "浏览器 agent 要执行的自然语言任务",
                    },
                    "expected": {"type": "string", "description": "预期结果"},
                },
                "required": ["name", "prompt"],
            },
        },
    },
]

_SYSTEM = (
    "你是测试平台的助手,在飞书群里回答关于测试项目的问题。"
    "可以用工具查真实数据(运行/问题/用例)或新建用例草稿。用简体中文简洁回答。"
    "不要编造数据——查不到就直说没有。跑测试/重跑暂不支持,让用户去网页触发。"
)


async def _exec_tool(session, project_id: int | None, name: str, args: dict) -> str:
    if project_id is None:
        return "没有绑定/识别到项目,无法查询。请先在群里发「@机器人 绑定 <项目名>」。"
    if name == "list_recent_runs":
        limit = min(int(args.get("limit") or 5), 20)
        rows = (
            (
                await session.execute(
                    select(Run)
                    .where(Run.project_id == project_id)
                    .order_by(Run.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return "该项目还没有运行记录。"
        return "\n".join(
            f"#{r.id} {r.name} · {r.status} · {r.passed_count}/{r.total_count} 通过 · {r.finished_at or '未完成'}"
            for r in rows
        )
    if name == "list_open_issues":
        q = select(Issue).where(Issue.project_id == project_id)
        status = args.get("status")
        q = q.where(Issue.status == status) if status else q.where(Issue.status != "closed")
        rows = (await session.execute(q.order_by(Issue.id.desc()).limit(20))).scalars().all()
        if not rows:
            return "没有符合条件的问题。"
        return f"共 {len(rows)} 条:\n" + "\n".join(
            f"#{i.id} [{i.severity}/{i.status}] {i.title}" for i in rows
        )
    if name == "count_cases":
        total = (
            await session.execute(
                select(func.count()).select_from(TestCase).where(TestCase.project_id == project_id)
            )
        ).scalar_one()
        enabled = (
            await session.execute(
                select(func.count())
                .select_from(TestCase)
                .where(TestCase.project_id == project_id, TestCase.enabled == True)  # noqa: E712
            )
        ).scalar_one()
        return f"用例 {total} 个,其中启用 {enabled} 个。"
    if name == "create_case_draft":
        from app.api import _next_case_key

        key = await _next_case_key(session, project_id)
        c = TestCase(
            project_id=project_id,
            case_key=key,
            name=args.get("name") or "未命名用例",
            prompt=args.get("prompt") or "",
            expected=args.get("expected") or "",
            status="draft",
        )
        session.add(c)
        await session.flush()
        return f"已创建用例草稿 {key}:{c.name}(id={c.id},draft,待人工确认启用)。"
    return f"未知工具 {name}"


async def agent_reply(session, text: str, context: str, project_id: int | None) -> str:
    """Run a bounded tool-calling loop and return the reply text."""
    client = await openai_client()
    model = (await llm_config()).model
    ctx = f"【最近群聊】\n{context}\n\n" if context else ""
    proj = f"当前项目 id={project_id}。" if project_id is not None else "尚未确定所属项目。"
    messages: list = [
        {"role": "system", "content": f"{_SYSTEM} {proj}"},
        {"role": "user", "content": f"{ctx}{text}"},
    ]
    for _ in range(4):
        try:
            resp = await client.chat.completions.create(
                model=model, temperature=0.2, messages=messages, tools=_TOOLS
            )
        except Exception:
            # Gateway may not support function-calling — answer without tools.
            log.warning("feishu agent: tools call failed, retrying without tools", exc_info=True)
            resp = await client.chat.completions.create(
                model=model, temperature=0.2, messages=messages
            )
            return (resp.choices[0].message.content or "").strip()
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip()
        messages.append(msg.model_dump())
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await _exec_tool(session, project_id, tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "(处理步骤过多,请把问题说得更具体些,或去网页查看)"

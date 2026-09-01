"""Runnable check: the judge is given a criterion and real evidence.

VRS run 37 actually created the record — the final screenshot showed
「单号 VRSSZ01-260827-0003 已通过」 — and the judge still failed it:
「缺少明确的预期结果且仅有代理自述成功，未提供足够证据」. Both halves of that reason
were the wiring's fault, not the run's: `expected` was empty (so there was no criterion
to match) and the judge only ever received action NAMES ("click", "input"), never the
browser's read-backs. Any case without an expected outcome was therefore unpassable.

python -m pytest tests/test_judge_prompt.py
"""

from __future__ import annotations

import json

from app.judge import _SYSTEM, build_content, build_prompt

ACTIONS = ["click", "input", "click"]
EVIDENCE = [
    'Clicked div role=option "行政楼一楼接洽区 QY001"',
    "Typed '13800138000'",
    "",  # steps with neither result nor error carry no evidence
    "单号 VRSSZ01-260827-0003 已通过",
]


def test_task_is_the_fallback_criterion_when_expected_is_empty() -> None:
    payload = json.loads(build_prompt("", "任务已完成。", ACTIONS, task="新建一条临时预约访客单"))

    assert payload["task"] == "新建一条临时预约访客单", (
        "with `expected` empty the task is the only criterion the judge has — it must be sent"
    )
    assert "EXPECTED is empty" in _SYSTEM, (
        "the system prompt must tell the judge to fall back to TASK, else an unfilled "
        "expected outcome silently fails every run"
    )


def test_step_results_are_passed_as_evidence() -> None:
    payload = json.loads(build_prompt("单号已生成", "任务已完成。", ACTIONS, evidence=EVIDENCE))

    assert payload["step_results"] == [
        'Clicked div role=option "行政楼一楼接洽区 QY001"',
        "Typed '13800138000'",
        "单号 VRSSZ01-260827-0003 已通过",
    ], "empty entries must be dropped, the rest kept in order"
    assert payload["actions"] == ACTIONS, "action names stay — they are the shape of the run"


def test_long_runs_are_truncated_on_both_lists() -> None:
    payload = json.loads(
        build_prompt("x", "y", ["click"] * 200, evidence=[f"step {i}" for i in range(200)])
    )
    assert len(payload["actions"]) == 80
    assert len(payload["step_results"]) == 80


def test_the_final_screenshot_is_attached_as_an_image() -> None:
    """The proof that a record was created is on screen. A text-only judge kept failing
    runs that visibly succeeded, asking for 「浏览器证据」 it was structurally never given."""
    content = build_content("{}", "AAAA")

    assert isinstance(content, list), "with a screenshot the user message must be multimodal"
    kinds = [part["type"] for part in content]
    assert kinds == ["text", "image_url"], f"unexpected content parts: {kinds}"
    assert content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"
    assert "FINAL SCREENSHOT" in _SYSTEM, (
        "the judge must be told the image is the page's own end state, not a claim"
    )


def test_no_screenshot_falls_back_to_a_plain_text_message() -> None:
    assert build_content("{}", None) == "{}"
    assert build_content("{}", "") == "{}"

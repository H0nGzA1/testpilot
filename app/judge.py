"""LLM-as-judge: given the expected outcome and what the agent actually did,
decide pass / fail. Errs toward 'failed' when evidence is thin (design doc §5.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.llm import llm_config, openai_client

_SYSTEM = (
    "You are a strict QA judge for an automated browser test. "
    "Given the test's EXPECTED outcome and the agent's FINAL result plus its action log, "
    "decide whether the test passed. Pass ONLY if the evidence clearly shows the expected "
    "outcome was achieved. If the evidence is missing, ambiguous, or the agent errored, "
    'return failed. Reply with JSON only: {"status": "passed"|"failed", "reason": "<one sentence>"}.'
    # Without these rules an empty `expected` made every case unpassable: there was no
    # criterion to match and nothing but the agent's own claim to match it against, so the
    # judge always answered "no expected outcome / only self-reported success".
    " When EXPECTED is empty or missing, judge against TASK instead: the test passes when "
    "the evidence shows the agent demonstrably did what TASK asked. Never fail a test merely "
    "because EXPECTED was not filled in. "
    "STEP_RESULTS are the browser's own observations — what was actually clicked or typed, "
    "the text it read back, and any errors. They are evidence. FINAL_ANSWER is only the "
    "agent's self-report; corroborate it against STEP_RESULTS rather than dismissing it. "
    # The screenshot is why a run that visibly created its record used to fail: the proof was
    # on screen and the judge could not see it, so it kept asking for "browser evidence".
    "The attached image is the FINAL SCREENSHOT of the page when the run ended — the page's "
    "own state, not a claim. It is the strongest evidence you have: read it. If it shows the "
    "expected outcome (the new row in the list, the success dialog, the error message, the "
    "disabled field), that settles it and you should pass. Judge on the evidence you were "
    "given; do not fail a run for lacking a particular form of proof it was never asked to "
    "produce. Note that the screenshot is the LAST frame only — an outcome that appeared "
    "earlier and was then dismissed will not be in it, so weigh STEP_RESULTS for those."
)


@dataclass(frozen=True)
class Verdict:
    status: str  # passed | failed
    reason: str


def build_prompt(
    expected: str,
    final_answer: str,
    actions: list[str],
    task: str = "",
    evidence: list[str] | None = None,
) -> str:
    """The judge's user message. Split out so the wiring is testable without an LLM call."""
    return json.dumps(
        {
            "task": task,
            "expected": expected,
            "final_answer": final_answer,
            "actions": actions[:80],
            "step_results": [e for e in (evidence or []) if e][:80],
        },
        ensure_ascii=False,
    )


def build_content(user: str, screenshot_b64: str | None) -> Any:
    """Multimodal user content when there's a final screenshot, plain text otherwise."""
    if not screenshot_b64:
        return user
    return [
        {"type": "text", "text": user},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
        },
    ]


async def judge(
    expected: str,
    final_answer: str,
    actions: list[str],
    task: str = "",
    evidence: list[str] | None = None,
    screenshot_b64: str | None = None,
) -> Verdict:
    user = build_prompt(expected, final_answer, actions, task, evidence)
    s = get_settings()
    system = f'{_SYSTEM} Write the "reason" in {s.report_language}.'
    cfg = await llm_config()
    client = await openai_client()

    async def ask(content: Any) -> Verdict:
        resp = await client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        status = "passed" if data.get("status") == "passed" else "failed"
        return Verdict(status=status, reason=str(data.get("reason", ""))[:500])

    try:
        try:
            return await ask(build_content(user, screenshot_b64))
        except Exception:
            if not screenshot_b64:
                raise
            # a gateway model without vision must not cost us the verdict entirely
            return await ask(user)
    except Exception as exc:  # judge failure must not pass a test by default
        return Verdict(status="failed", reason=f"judge_error: {type(exc).__name__}: {exc}"[:500])
    finally:
        await client.close()

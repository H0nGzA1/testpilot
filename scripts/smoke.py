"""Phase-0 end-to-end smoke: seed one public-site test case, run it, print the verdict.

    python scripts/smoke.py

Requires deps installed (`uv pip install -e .` + `playwright install chromium`) and a
reachable LLM gateway. Uses the local sqlite DB from .env by default.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import db_session, init_db
from app.engine import run_suite
from app.models import Project, Run, RunResult, TestCase


async def main() -> None:
    await init_db()

    async with db_session() as session:
        project = Project(name="smoke", base_url="https://example.com")
        session.add(project)
        await session.flush()

        case = TestCase(
            project_id=project.id,
            name="homepage title",
            prompt="Open the page and report the main heading text you see.",
            expected="The page's main heading is 'Example Domain'.",
        )
        session.add(case)
        await session.flush()

        run = Run(project_id=project.id, name="smoke run", case_ids=[case.id], concurrency=1)
        session.add(run)
        await session.flush()
        run_id = run.id

    summary = await run_suite(run_id)
    print("SUMMARY:", summary)

    async with db_session() as session:
        results = (
            (await session.execute(select(RunResult).where(RunResult.run_id == run_id)))
            .scalars()
            .all()
        )
        for r in results:
            print(
                f"case={r.case_id} status={r.status} latency_ms={r.latency_ms}\n"
                f"  answer={r.final_answer!r}\n"
                f"  judge={r.judge_reason!r}\n"
                f"  video={r.video_url}\n  trace={r.trace_url}\n  error={r.error}"
            )


if __name__ == "__main__":
    asyncio.run(main())

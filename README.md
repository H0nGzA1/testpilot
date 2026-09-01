# TestPilot

**Agentic end-to-end testing platform** — write test cases in plain natural language, let a browser agent execute them in a real Chrome, and let an LLM judge decide pass/fail with evidence (video, screenshots, action trace).

[中文文档 / Chinese README](./README.zh-CN.md)

```
natural-language case ──▶ browser agent (browser-use → Playwright/CDP → Chromium)
                                │  video + screenshots + action history
                                ▼
                          LLM judge ──▶ pass / fail + reason ──▶ aggregated run report
```

## Why

Traditional E2E suites (Playwright/Cypress scripts) break every time a selector changes. TestPilot cases are *prompts*, not scripts:

> "Log in as the reviewer role, open the pending-approval list, approve the first entry, and verify its status changes to Approved."

The agent figures out the clicks; the judge reads the evidence and defaults to **failed** when the evidence is thin — no flaky green.

## Features

- **Natural-language test cases** — project-scoped, reusable, tagged, Excel (.xlsx) import/export
- **Real-browser execution** — one Chromium per case via [browser-use](https://github.com/browser-use/browser-use), with mp4 video, per-step screenshots, and a replayable action-history JSON
- **LLM-as-judge** — pass/fail with a written reason; conservative by design (thin evidence ⇒ failed); infra errors are retried and flaky passes are marked, judge failures are not retried
- **Bring your own model** — any OpenAI-compatible endpoint; base URL / key / models are configurable at runtime in **System settings** (no redeploy), with a separate optional agent model (e.g. a local VLM)
- **Runs & reports** — concurrent execution with a global browser budget, live progress over SSE, per-case replay, re-run *only failed* or *only errored* cases, run comparison
- **Environments & accounts** — per-project environments (test/staging/…), multiple login accounts with roles; session capture & reuse (cookies + localStorage + **sessionStorage** via CDP) so cases start logged in instead of burning steps on the login page
- **Issue tracking** — built-in Kanban; optional **two-way GitLab issue sync** (off by default — `ENABLE_GITLAB=true`)
- **Feishu (Lark) bot** — optional (off by default — `ENABLE_FEISHU=true`): bind a project to a group chat, trigger runs by chatting, result cards, feedback messages become issues, Bitable sync
- **Multi-user** — optional login, shared workspace or per-project owner/editor/viewer roles, email invites
- **Bilingual UI** — English / 简体中文

## Quick start (local dev)

Prereqs: Python ≥ 3.11, Node 20 + pnpm, and an OpenAI-compatible LLM endpoint (OpenAI itself, or any gateway/local VLM speaking the same API).

```bash
# backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
playwright install chromium
cp .env.example .env               # set GATEWAY_BASE_URL / GATEWAY_API_KEY / GATEWAY_MODEL

python -m pytest tests/            # self-check, no browser/LLM needed
python scripts/smoke.py            # end-to-end: real browser on example.com -> verdict
uvicorn app.main:app --port 8099   # API

# frontend (proxies /api and /artifacts to :8099)
cd web && pnpm install && pnpm dev # http://localhost:5180
```

## Docker deployment

One image runs the whole stack (API + SPA + Celery worker/beat + Feishu worker), plus bundled Postgres and Redis:

```bash
cp .env.example .env                                        # set TESTPILOT_SECRET_KEY etc.
docker build -f Dockerfile.base -t testpilot-base:latest .  # deps + Chromium (once)
docker compose build
docker compose up -d
open http://localhost:8000
```

See **[docs/deployment.md](docs/deployment.md)** for the full manual (image layout, scaling the browser budget, ports, migrations) and **[docs/configuration.md](docs/configuration.md)** for every setting.

## Project layout

```
app/
  config.py     settings (.env)
  models.py     Project · TestCase · Run · RunResult · Issue · User · …
  engine.py     run loop: concurrent drain + failure isolation + aggregation
  executor.py   one browser per case, recording, session capture/restore (CDP)
  judge.py      LLM-as-judge (defaults to 'failed' on thin evidence)
  llm.py        OpenAI-compatible clients (agent + judge)
  api.py        REST + SSE
  storage.py    artifacts: S3-compatible or local disk
  gitlab_*.py   two-way issue sync (Celery worker + beat)
  feishu*.py    Lark bot: commands, cards, feedback → issues, Bitable
web/            React + Vite + Tailwind SPA
alembic/        migrations (container entrypoint runs upgrade head)
docs/           deployment & configuration manuals, design specs
tests/          pytest suite (pure logic, no browser needed)
```

## How judging works

Each case produces: final URL trail, step-by-step action history with screenshots, and an mp4. The judge gets the case's expected outcome plus this evidence and must answer passed/failed **with a reason**, in your configured `REPORT_LANGUAGE`. Timeouts/connection errors count as *infra errors* (retried up to `CASE_RETRIES`, and a case that only passes on retry is flagged *flaky*); a judge "failed" is never retried.

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Run `ruff check .` and `python -m pytest tests/` before pushing.

## License

[MIT](LICENSE)

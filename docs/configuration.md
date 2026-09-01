# Configuration reference

All settings come from environment variables (or a `.env` file — copy `.env.example`).
Defaults shown are the code defaults from `app/config.py`.

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./testpilot.db` | SQLite for dev; use `postgresql+asyncpg://user:pass@host:5432/testpilot` in production. docker-compose wires this to the bundled Postgres automatically. |
| `POSTGRES_PASSWORD` | `testpilot` | Only used by docker-compose to provision the bundled `db` service and build `DATABASE_URL`. |

## Optional integrations

Both are **off by default** — a plain install needs neither. Enabling one shows its
settings UI and activates its endpoints/workers.

| Variable | Default | Notes |
|---|---|---|
| `ENABLE_GITLAB` | `false` | Two-way GitLab issue sync (also needs `REDIS_URL` + the GitLab settings below). |
| `ENABLE_FEISHU` | `false` | Feishu (Lark) bot + Bitable mirror. |

## LLM gateway

Both the browser agent and the judge speak the OpenAI API. Any OpenAI-compatible endpoint works (OpenAI, a corporate gateway, vLLM/Ollama serving a VLM, …).

The env values below are **defaults** — an admin can override base URL, API key, and
models at runtime in **System settings → LLM model** (key stored encrypted; changes
apply to new runs without a redeploy).

| Variable | Default | Notes |
|---|---|---|
| `GATEWAY_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL. |
| `GATEWAY_API_KEY` | *(empty)* | API key for that endpoint. |
| `GATEWAY_MODEL` | `gpt-4o` | Shared default model; the **judge always uses this**. Needs vision (screenshots are part of the evidence). |
| `AGENT_MODEL` | *(empty)* | Optional separate model for the browser agent; empty falls back to `GATEWAY_MODEL`. E.g. run the agent on a local VLM and keep a stronger judge. |
| `GATEWAY_VERIFY_SSL` | `true` | Set `false` for gateways with self-signed certificates. |
| `GATEWAY_MAX_TOKENS` | `16000` | Completion cap for the agent's structured output. browser-use needs a high cap — don't lower it casually. |
| `REPORT_LANGUAGE` | `Chinese (简体中文)` | Language for the agent's reasoning and the judge's written reason, e.g. `English`. |

## Artifact storage

| Variable | Default | Notes |
|---|---|---|
| `S3_ENDPOINT` | *(empty)* | Empty ⇒ store artifacts (videos, screenshots, history) on local disk under `ARTIFACT_DIR`. Set to any S3-compatible endpoint (MinIO, RustFS, AWS…) to upload instead. |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | *(empty)* | Credentials for the endpoint. |
| `S3_BUCKET` | `testpilot` | |
| `S3_REGION` | `us-east-1` | |
| `ARTIFACT_DIR` | `./artifacts` | Local artifact root (also the compose shared volume). |

## Security

| Variable | Default | Notes |
|---|---|---|
| `TESTPILOT_SECRET_KEY` | *(empty)* | **Required for stored credentials.** Fernet key encrypting test-account passwords/sessions at rest. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Empty ⇒ the credential API is disabled. |

## Execution limits

| Variable | Default | Notes |
|---|---|---|
| `CASE_TIMEOUT_S` | `60` | Hard wall-clock cap per case (login + task). A per-project override in the UI wins. |
| `CASE_MAX_STEPS` | `30` | Agent step budget per case. |
| `CASE_RETRIES` | `0` | Auto-retries for **infra errors only** (timeouts, connection failures). A case that passes only on retry is marked *flaky*. Judge failures are never retried. |
| `SESSION_TTL_MIN` | `25` | How long the app-under-test keeps a login session alive. A captured login is re-used until this expires, then re-captured once (single-flight). Keep it just under the real session lifetime. |
| `DEFAULT_CONCURRENCY` | `2` | Per-run worker count (in-process fallback only). |
| `MAX_GLOBAL_CONCURRENCY` | `16` | Global ceiling on concurrent browsers across **all** runs/users (~0.5 GB RAM each). With Celery this **must** equal the worker's `--concurrency` — compose reads it from `.env` and does this for you. |

## GitLab issue sync (optional)

Two-way sync between the built-in Kanban and a GitLab project. Requires `ENABLE_GITLAB=true` **and** `REDIS_URL`; otherwise issues stay local and creation never blocks.

| Variable | Default | Notes |
|---|---|---|
| `REDIS_URL` | *(empty)* | Celery broker/result backend, e.g. `redis://localhost:6379/0`. Compose wires the bundled Redis. |
| `GITLAB_BASE_URL` | `https://gitlab.com/api/v4` | Your GitLab instance's API v4 base. |
| `GITLAB_TOKEN` | *(empty)* | Optional server-wide `api`-scope token; projects then only pick a GitLab project in the UI. A per-project token (stored encrypted) overrides it. |
| `GITLAB_VERIFY_SSL` | `true` | |
| `GITLAB_POLL_INTERVAL_S` | `60` | Beat poll interval for pulling status/label/comment changes back. |

## Auth / multi-user (optional)

| Variable | Default | Notes |
|---|---|---|
| `AUTH_ENABLED` | `false` | Require login on every endpoint. |
| `SHARED_WORKSPACE` | `false` | `true`: any logged-in user has full access to every project (login gate only). `false`: per-project RBAC via owner/editor/viewer membership; admins see all. |
| `JWT_SECRET` | *(empty)* | HS256 signing key (`openssl rand -hex 32`); required once `AUTH_ENABLED=true`. |
| `JWT_TTL_HOURS` | `168` | Session cookie lifetime. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | *(empty)* | Seed the first admin on first startup when no users exist. |
| `PUBLIC_BASE_URL` | *(empty)* | Canonical public URL — drives invite-email links and the address shown in the UI. |

### Invite emails (SMTP)

Best-effort: a send failure is logged, never raised — an invite still returns a copyable link.

| Variable | Default |
|---|---|
| `EMAIL_FROM` | `noreply@example.com` |
| `EMAIL_HOST` / `EMAIL_PORT` | `smtp.example.com` / `25` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | *(empty — unauthenticated relay)* |
| `EMAIL_USE_SSL` / `EMAIL_USE_TLS` | `false` / `false` |

## Feishu (Lark) bot (optional)

Requires `ENABLE_FEISHU=true`. Create a self-built app on the Feishu open platform, enable the long-connection (WebSocket) event mode, then either set these or configure them at runtime in **System settings** in the UI.

| Variable | Default | Notes |
|---|---|---|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | *(empty)* | Empty ⇒ bot disabled. |
| `FEISHU_VERIFICATION_TOKEN` | *(empty)* | Event-subscription verification token; when set, incoming events must match. |
| `FEISHU_API_BASE` | `https://open.feishu.cn` | Use `https://open.larksuite.com` for international Lark. |
| `FEISHU_AUTO_ANSWER_DETECTED` | `true` | Also answer questions detected from context, not just @-mentions / DMs. |
| `FEISHU_AMBIENT_REQUIRE_KEYWORD` | `true` | Cost gate: non-@ messages need a problem keyword before the LLM classifies them. `false` ⇒ classify every message (higher cost). |

## Serving the SPA

| Variable | Default | Notes |
|---|---|---|
| `WEB_DIST` | *(empty)* | Path to the built frontend, served by the API at `/`. The Docker image sets `/app/web_dist`; leave empty in dev (Vite serves the SPA). |

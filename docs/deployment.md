# Deployment manual

## Architecture

One image runs every process; docker-compose starts the full stack:

| Service | Role |
|---|---|
| `db` | Postgres 16 (data) |
| `redis` | Redis 7 (Celery broker) |
| `api` | FastAPI — REST + SSE + serves the built SPA at `/`. Runs `alembic upgrade head` on start. |
| `worker` | Celery worker — executes test cases (each case = one Chromium) and GitLab sync tasks |
| `beat` | Celery beat — polls GitLab for issue changes |
| `feishu` | Feishu bot long-connection worker (dials **out** to Feishu — no public callback URL needed). Idle until the bot is configured. |

## Image layout (two layers)

- **`Dockerfile.base`** (`testpilot-base`) — Python 3.11 + every dependency from
  `pyproject.toml` + Playwright Chromium + its OS libs. Rebuild only when
  `Dockerfile.base` or `pyproject.toml` change (slow: downloads Chromium).
- **`Dockerfile`** — stage 1 builds the Vite SPA (`node:20-slim`), stage 2 starts
  `FROM` the base and only copies `app/`, `alembic/`, and the built frontend.
  Installs nothing, so day-to-day builds take seconds.

## First deployment

```bash
git clone <your-fork> testpilot && cd testpilot
cp .env.example .env
```

Edit `.env` — the minimum for a real deployment:

- `TESTPILOT_SECRET_KEY` — Fernet key (see [configuration.md](configuration.md#security))
- `GATEWAY_BASE_URL` / `GATEWAY_API_KEY` / `GATEWAY_MODEL` — your LLM endpoint
- `POSTGRES_PASSWORD` — anything but the default
- For multi-user: `AUTH_ENABLED=true`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `PUBLIC_BASE_URL`

Then:

```bash
docker build -f Dockerfile.base -t testpilot-base:latest .   # once
docker compose build
docker compose up -d
curl -f http://localhost:8000/health
```

Open `http://<host>:8000` — API and UI share one origin.

## Upgrades

```bash
git pull
docker compose build          # fast — base unchanged
docker compose up -d          # api runs alembic upgrade head on start
```

Rebuild the base first only if `pyproject.toml` or `Dockerfile.base` changed.

The worker has `stop_grace_period: 12m`: a deploy during a run waits for in-flight
cases (up to their timeout) instead of SIGKILLing them mid-browser — killed cases
are already acked and would be silently lost.

## Sizing the browser budget

Each running case is one Chromium (~0.5 GB RAM). `MAX_GLOBAL_CONCURRENCY` is the
global ceiling and **is** the Celery worker's `--concurrency` (compose wires it).
Default 16 ≈ 8 GB peak. Size it to the host's free RAM.

## Ports / reverse proxy

The API listens on 8000. To publish on another port, add a
`docker-compose.override.yml`:

```yaml
services:
  api:
    ports: !override ["8010:8000"]
```

Behind nginx/Caddy, proxy to `:8000` and keep SSE unbuffered
(`proxy_buffering off;` for `/api/…/events`).

## Internal DNS

If the app under test resolves only through an internal resolver, uncomment the
`dns:` block in `docker-compose.yml` — containers otherwise use public DNS and
will NXDOMAIN internal names.

## Migrations

- `api` runs `alembic upgrade head` at start (`RUN_MIGRATIONS=1` default).
- `worker` / `beat` / `feishu` set `RUN_MIGRATIONS=0` so exactly one process migrates.
- Manual: `docker compose exec api alembic upgrade head`.

## Artifacts

Videos/screenshots/history live in the shared `artifacts` volume (`ARTIFACT_DIR`),
served by the API at `/artifacts/…`. Point `S3_ENDPOINT` at any S3-compatible
store to upload instead (see [configuration.md](configuration.md#artifact-storage)).

## Running without Docker

```bash
uv pip install -e .
playwright install --with-deps chromium
cd web && pnpm install && pnpm build && cd ..
export WEB_DIST=$PWD/web/dist
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
# optional, for GitLab sync + queued runs:
celery -A app.celery_app.celery worker -l info --concurrency=16
celery -A app.celery_app.celery beat -l info
python -m app.feishu_ws        # optional Feishu bot
```

Without `REDIS_URL`, runs execute in-process in the API (fine for small setups)
and GitLab sync stays disabled.

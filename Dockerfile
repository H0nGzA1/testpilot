# ============================================
# TestPilot app image
# ============================================
# Stage 1 builds the Vite frontend; stage 2 is the runtime — it FROM's the base
# image (which already has every Python dep + Chromium) and only layers app code
# and the built frontend on top. Installs NOTHING, so builds are fast.
#
# Build args:
#   BASE_IMAGE : base with all deps + Chromium (build it first from Dockerfile.base)
#   NODE_IMAGE : node image for the web build
#   APP_VERSION: release tag, surfaced later if needed
# ============================================

ARG BASE_IMAGE=testpilot-base:latest
ARG NODE_IMAGE=node:20-slim
ARG APP_VERSION=dev
# Optional npm registry mirror (e.g. https://registry.npmmirror.com) for networks
# where npmjs.org is slow/unreachable. Empty => npm default.
ARG NPM_REGISTRY=""

# ---- stage 1: build the SPA ----
FROM ${NODE_IMAGE} AS web
ARG NPM_REGISTRY
WORKDIR /web
RUN if [ -n "$NPM_REGISTRY" ]; then npm config -g set registry "$NPM_REGISTRY"; fi \
    && npm install -g pnpm@9
COPY web/package.json web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY web/ ./
RUN pnpm build   # -> /web/dist

# ---- stage 2: runtime ----
FROM ${BASE_IMAGE}
ARG APP_VERSION=dev

WORKDIR /app

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Built frontend, served by FastAPI (WEB_DIST).
COPY --from=web /web/dist ./web_dist

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_VERSION=${APP_VERSION} \
    WEB_DIST=/app/web_dist \
    ARTIFACT_DIR=/app/artifacts \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Non-root; owns the app + a writable artifacts dir.
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/artifacts \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint runs `alembic upgrade head` (unless RUN_MIGRATIONS=0) then exec's CMD.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

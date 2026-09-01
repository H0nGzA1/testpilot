#!/bin/sh
# Run pending migrations (api container only), then exec the real CMD
# (uvicorn / celery worker / celery beat). Fail fast if migrations fail.
# Worker/beat set RUN_MIGRATIONS=0 so only one process migrates.
set -e

cd /app
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] alembic upgrade head"
    alembic upgrade head
fi

exec "$@"

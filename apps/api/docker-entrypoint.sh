#!/bin/sh
# Container startup: run migrations, optionally seed fictional data, then serve.
set -e

echo "[entrypoint] applying database migrations..."
alembic upgrade head

if [ "${SEED_ON_START}" = "true" ]; then
  echo "[entrypoint] seeding fictional demo data (idempotent)..."
  python -m app.seed.seed_data || echo "[entrypoint] seed skipped/failed (non-fatal)"
fi

echo "[entrypoint] starting API on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

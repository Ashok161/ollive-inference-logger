#!/bin/sh
set -eu

PORT="${PORT:-8000}"
export INGESTION_URL="${INGESTION_URL:-http://127.0.0.1:${PORT}/v1/ingest}"

if [ "${EMBED_WORKER:-true}" = "true" ]; then
  echo "Starting embedded worker…"
  python /app/worker.py &
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"

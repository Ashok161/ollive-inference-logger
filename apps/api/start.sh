#!/bin/sh
set -eu

PORT="${PORT:-8000}"
export INGESTION_URL="${INGESTION_URL:-http://127.0.0.1:${PORT}/v1/ingest}"

if [ "${EMBED_REDIS:-true}" = "true" ]; then
  echo "Starting embedded Redis…"
  redis-server --daemonize yes --port 6379 --save "" --appendonly no --bind 127.0.0.1
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
  sleep 1
fi

if [ "${EMBED_WORKER:-true}" = "true" ]; then
  echo "Starting embedded worker…"
  python /app/worker.py &
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"

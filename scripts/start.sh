#!/bin/sh
set -e

# Apply migrations with a few retries: the managed Postgres proxy
# occasionally drops a connection mid-statement (observed as SSL EOF /
# connection reset by peer). Previously a single failed migration
# attempt killed the boot, and Railway marked the deploy as
# "1/1 replicas never became healthy".
attempt=0
until /app/.venv/bin/alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 5 ]; then
    echo "alembic upgrade head failed after $attempt attempts; aborting" >&2
    exit 1
  fi
  echo "alembic upgrade head failed (attempt $attempt); retrying in 5s" >&2
  sleep 5
done

# Use the build-time venv binaries directly — `uv run` re-syncs the
# project (re-downloading dev deps like ruff/mypy) and costs 10-15s of
# the healthcheck window on every boot.
exec /app/.venv/bin/uvicorn podking.main:app --host 0.0.0.0 --port "${PORT:-8000}"

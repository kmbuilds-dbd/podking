#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
evidence_dir="$repo_root/verification-artifacts/podking"
run_dir="/private/tmp/podking-verify-8011-$$"
pid_file="/tmp/podking-verify-8011.pid"
port=8011

mkdir -p "$evidence_dir" "$run_dir"
rm -f "$evidence_dir/run.log" "$evidence_dir/server.log"

cleanup() {
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      wait "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
  rm -rf "$run_dir"
}
trap cleanup EXIT

exec > >(tee "$evidence_dir/run.log") 2>&1

cd "$repo_root"
npm --prefix frontend run build

database_url="${TEST_DATABASE_URL:-postgresql+asyncpg://podking:podking@localhost:5432/podking_test}"
DATABASE_URL="$database_url" \
  SESSION_SECRET_KEY="verify-session-secret-at-least-32-bytes" \
  FERNET_KEY="g9g_Lr-HRfT7ORu6rcs3RY4g09Mw6Un5WlKT99rkY7o=" \
  ALLOWED_EMAILS="allowed@example.com" \
  AUDIO_STORAGE_PATH="$run_dir/audio" \
  .venv/bin/alembic upgrade head

TEST_MODE=1 \
  DATABASE_URL="$database_url" \
  SESSION_SECRET_KEY="verify-session-secret-at-least-32-bytes" \
  FERNET_KEY="g9g_Lr-HRfT7ORu6rcs3RY4g09Mw6Un5WlKT99rkY7o=" \
  ALLOWED_EMAILS="allowed@example.com" \
  AUDIO_STORAGE_PATH="$run_dir/audio" \
  APP_BASE_URL="http://127.0.0.1:$port" \
  .venv/bin/uvicorn podking.main:app --host 127.0.0.1 --port "$port" >"$evidence_dir/server.log" 2>&1 &
server_pid=$!
echo "$server_pid" > "$pid_file"

ready=0
for attempt in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$port/healthz" >"$run_dir/healthz.json"; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" -eq 1
kill -0 "$server_pid"

cd "$repo_root/frontend"
E2E_BASE_URL="http://127.0.0.1:$port" npx playwright test

cd "$repo_root"
DATABASE_URL="$database_url" \
  SESSION_SECRET_KEY="verify-session-secret-at-least-32-bytes" \
  FERNET_KEY="g9g_Lr-HRfT7ORu6rcs3RY4g09Mw6Un5WlKT99rkY7o=" \
  ALLOWED_EMAILS="allowed@example.com" \
  AUDIO_STORAGE_PATH="$run_dir/audio" \
  .venv/bin/pytest tests/test_transcriptions.py

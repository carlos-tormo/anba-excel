#!/usr/bin/env bash
set -euo pipefail

if [ ! -f /data/league.db ]; then
  mkdir -p /data
  cp data/league.db /data/league.db
fi

export OWNER_BACKGROUND_UPLOAD_DIR="${OWNER_BACKGROUND_UPLOAD_DIR:-/data/uploads/owner-office}"

python3 app/server.py --db /data/league.db --host 0.0.0.0 --port "${PORT:-8000}" &
web_pid=$!

python3 -m app.workers.discord_waiting_list_bot --db /data/league.db &
worker_pid=$!

trap 'kill "$web_pid" "$worker_pid" 2>/dev/null || true' TERM INT

wait -n "$web_pid" "$worker_pid"
exit_code=$?
kill "$web_pid" "$worker_pid" 2>/dev/null || true
exit "$exit_code"

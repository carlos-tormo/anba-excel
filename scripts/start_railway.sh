#!/usr/bin/env bash
set -euo pipefail

if [ ! -f /data/league.db ]; then
  mkdir -p /data
  cp data/league.db /data/league.db
fi

export OWNER_BACKGROUND_UPLOAD_DIR="${OWNER_BACKGROUND_UPLOAD_DIR:-/data/uploads/owner-office}"

python_bin="${PYTHON_BIN:-/opt/venv/bin/python}"
if [ ! -x "$python_bin" ]; then
  python_bin="$(
    command -v python \
      || command -v python3 \
      || command -v python3.12 \
      || find /nix /opt /root /usr -path "*/bin/python*" -type f -perm -111 2>/dev/null | head -n 1 \
      || true
  )"
fi
if [ -z "$python_bin" ]; then
  echo "No Python interpreter found. Expected /opt/venv/bin/python, python on PATH, or a Python binary under /nix /opt /root /usr." >&2
  exit 127
fi
echo "Using Python: $python_bin"

"$python_bin" app/server.py --db /data/league.db --host 0.0.0.0 --port "${PORT:-8000}" &
web_pid=$!

worker_pid=""
start_waiting_list_worker() {
  local delay="${WAITING_LIST_WORKER_RESTART_DELAY_SECONDS:-900}"
  while true; do
    if "$python_bin" -m app.workers.discord_waiting_list_bot --db /data/league.db; then
      status=0
    else
      status=$?
    fi
    echo "Discord waiting-list worker exited with status ${status}; retrying in ${delay}s without stopping web." >&2
    sleep "$delay"
  done
}

if [ "${WAITING_LIST_DISCORD_WORKER_ENABLED:-true}" != "false" ] && [ -n "${DISCORD_BOT_TOKEN:-}" ]; then
  start_waiting_list_worker &
  worker_pid=$!
else
  echo "Discord waiting-list worker disabled or DISCORD_BOT_TOKEN is not set; web will continue without worker." >&2
fi

trap 'kill "$web_pid" ${worker_pid:-} 2>/dev/null || true' TERM INT

wait "$web_pid"
exit_code=$?
kill ${worker_pid:-} 2>/dev/null || true
exit "$exit_code"

#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Cross-platform DIG start script. Works on Linux + macOS.
#
# Usage:
#   ./scripts/dig-start.sh                      # detached, write PIDs, print URLs
#   ./scripts/dig-start.sh --foreground         # stay foreground, prefixed logs, Ctrl-C cleans up
#   ./scripts/dig-start.sh --api-port 9000      # override API port for this run
#   ./scripts/dig-start.sh --web-port 4000      # override web port for this run
#   ./scripts/dig-start.sh --data-dir /var/dig  # override data directory
#   ./scripts/dig-start.sh --save               # persist any --*-port / --data-dir flags to config
#
# Defaults: api 127.0.0.1:8090  · web 127.0.0.1:3000  · data <repo>/data
# Persistent overrides live at ~/.config/dig/config.json — see scripts/dig_config.py.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"

# ---- portable helpers ----
err() { printf '%s\n' "$*" >&2; }

# Find a Python 3 interpreter that's actually present on either Linux or macOS.
PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
  err "python3 not found in PATH — required for the config helper."
  exit 127
fi

# ---- parse CLI flags ----
FOREGROUND=0
SAVE=0
CLI_API_PORT=""
CLI_WEB_PORT=""
CLI_DATA_DIR=""
CLI_API_HOST=""
CLI_WEB_HOST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground|-f) FOREGROUND=1; shift ;;
    --save)          SAVE=1; shift ;;
    --api-port)      CLI_API_PORT="${2:?--api-port needs a value}"; shift 2 ;;
    --web-port)      CLI_WEB_PORT="${2:?--web-port needs a value}"; shift 2 ;;
    --api-host)      CLI_API_HOST="${2:?--api-host needs a value}"; shift 2 ;;
    --web-host)      CLI_WEB_HOST="${2:?--web-host needs a value}"; shift 2 ;;
    --data-dir)      CLI_DATA_DIR="${2:?--data-dir needs a value}"; shift 2 ;;
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

# Apply CLI overrides as env vars so dig_config picks them up.
[[ -n "$CLI_API_PORT" ]] && export DIG_API_PORT="$CLI_API_PORT"
[[ -n "$CLI_WEB_PORT" ]] && export DIG_WEB_PORT="$CLI_WEB_PORT"
[[ -n "$CLI_API_HOST" ]] && export DIG_API_HOST="$CLI_API_HOST"
[[ -n "$CLI_WEB_HOST" ]] && export DIG_WEB_HOST="$CLI_WEB_HOST"
[[ -n "$CLI_DATA_DIR" ]] && export DIG_DATA_DIR="$CLI_DATA_DIR"

# Persist if requested.
if [[ "$SAVE" -eq 1 ]]; then
  [[ -n "$CLI_API_PORT" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set api.port "$CLI_API_PORT" >/dev/null
  [[ -n "$CLI_WEB_PORT" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set web.port "$CLI_WEB_PORT" >/dev/null
  [[ -n "$CLI_API_HOST" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set api.host "$CLI_API_HOST" >/dev/null
  [[ -n "$CLI_WEB_HOST" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set web.host "$CLI_WEB_HOST" >/dev/null
  [[ -n "$CLI_DATA_DIR" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set dataDir "$CLI_DATA_DIR" >/dev/null
  err "[dig start] persisted overrides to $("$PY" "$SCRIPT_DIR/dig_config.py" path 2>/dev/null || true)"
fi

# Resolve effective config and bring values into the shell.
EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export)" || { err "config resolve failed"; exit 1; }
eval "$EXPORT"

API_HOST="${DIG_API_HOST:-127.0.0.1}"
API_PORT="${DIG_API_PORT:-8090}"
WEB_HOST="${DIG_WEB_HOST:-127.0.0.1}"
WEB_PORT="${DIG_WEB_PORT:-3000}"

# Where to put PIDs + logs. Use XDG_CONFIG_HOME on both Linux and macOS.
USER_CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/dig"
mkdir -p "$USER_CFG_DIR"
PID_FILE="$USER_CFG_DIR/pid.json"

LOG_DIR="${DIG_LOG_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$LOG_DIR"
API_LOG="$LOG_DIR/dig-api.log"
WEB_LOG="$LOG_DIR/dig-web.log"

# ---- preflight ----
if [[ ! -d "$REPO_ROOT/backend/.venv" ]]; then
  err "[dig start] backend venv missing — run 'make backend-setup' first."
  exit 1
fi
if [[ ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
  err "[dig start] frontend deps missing — run 'pnpm install' from the repo root first."
  exit 1
fi

# Refuse to start if anything is already LISTENING on the requested ports.
# `-sTCP:LISTEN` matters — without the filter, lingering CLOSED / TIME_WAIT /
# CLOSE_WAIT sockets (e.g. left by a recently-killed dev process or a client
# that connected and hung up) trigger a spurious "port already in use" error
# even though nothing is actually serving. The other dig-* scripts
# (dig-stop, dig-restart, dig-restart-web) already filter to LISTEN — keep
# this one consistent.
if command -v lsof >/dev/null 2>&1; then
  if lsof -ti tcp:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    err "[dig start] port $API_PORT already in use. Stop it first or pass --api-port N."
    exit 2
  fi
  if lsof -ti tcp:"$WEB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    err "[dig start] port $WEB_PORT already in use. Stop it first or pass --web-port N."
    exit 2
  fi
fi

cat <<EOF
[dig start] api  → http://$API_HOST:$API_PORT
[dig start] web  → http://$WEB_HOST:$WEB_PORT
[dig start] cfg  → $("$PY" "$SCRIPT_DIR/dig_config.py" path 2>/dev/null || echo '(defaults only)')
EOF

# Foreground mode: prefix-tag and inherit signals; for `make dev` and Ctrl-C use.
if [[ "$FOREGROUND" -eq 1 ]]; then
  exec "$SCRIPT_DIR/dig-dev.sh"
fi

# ---- detached mode ----
# Try to start with `setsid` (linux) or `nohup` (mac + linux) so the children
# survive shell exit. setsid is preferred because it gives us a process group
# we can kill cleanly later.
START_PREFIX=()
if command -v setsid >/dev/null 2>&1; then
  START_PREFIX=(setsid)
elif command -v nohup >/dev/null 2>&1; then
  START_PREFIX=(nohup)
fi

cd "$REPO_ROOT/backend"
DIG_HOST="$API_HOST" DIG_PORT="$API_PORT" \
  "${START_PREFIX[@]}" "$REPO_ROOT/backend/.venv/bin/dig-api" \
    > "$API_LOG" 2>&1 &
API_PID=$!

# next dev — set NEXT_PUBLIC_DIG_API so the in-browser client knows where to call.
cd "$REPO_ROOT/frontend"
NEXT_PUBLIC_DIG_API="http://$API_HOST:$API_PORT" PORT="$WEB_PORT" HOSTNAME="$WEB_HOST" \
  "${START_PREFIX[@]}" pnpm dev --port "$WEB_PORT" --hostname "$WEB_HOST" \
    > "$WEB_LOG" 2>&1 &
WEB_PID=$!

# Persist PIDs so dig-stop can find them.
"$PY" - "$PID_FILE" "$API_PID" "$WEB_PID" "$API_PORT" "$WEB_PORT" "$API_LOG" "$WEB_LOG" <<'PYEOF'
import json, sys
path, api_pid, web_pid, api_port, web_port, api_log, web_log = sys.argv[1:]
data = {
    "api": {"pid": int(api_pid), "port": int(api_port), "log": api_log},
    "web": {"pid": int(web_pid), "port": int(web_port), "log": web_log},
}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF

# Wait for both endpoints to start serving.
ready_api=0
ready_web=0
for i in $(seq 1 60); do
  if [[ "$ready_api" -eq 0 ]] && curl -sf "http://$API_HOST:$API_PORT/health" >/dev/null 2>&1; then
    ready_api=1
    echo "[dig start] api ready (${i}s)"
  fi
  if [[ "$ready_web" -eq 0 ]] && curl -sf -o /dev/null "http://$WEB_HOST:$WEB_PORT/" 2>&1; then
    ready_web=1
    echo "[dig start] web ready (${i}s)"
  fi
  if [[ "$ready_api" -eq 1 && "$ready_web" -eq 1 ]]; then break; fi
  sleep 1
done

if [[ "$ready_api" -eq 0 || "$ready_web" -eq 0 ]]; then
  err "[dig start] one or both services failed to start within 60s."
  err "  api log: $API_LOG"
  err "  web log: $WEB_LOG"
  exit 3
fi

cat <<EOF

✅ DIG is running.
   web:  http://$WEB_HOST:$WEB_PORT
   api:  http://$API_HOST:$API_PORT
   pids: api=$API_PID web=$WEB_PID
   logs: $API_LOG  ·  $WEB_LOG
   stop: ./scripts/dig-stop.sh
EOF

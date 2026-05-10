#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Cross-platform DIG API restart script. Works on Linux + macOS.
#
# Usage:
#   ./scripts/dig-restart.sh           # graceful TERM, escalate after 5s, re-launch API
#   ./scripts/dig-restart.sh --force   # SIGKILL the API immediately, re-launch
#
# Restarts ONLY the backend API process (`dig-api` / uvicorn). The Next.js
# dev server is left running, no browsers are touched. The frontend's
# server-status overlay will flip red while the API is down and back to
# green once `/health` answers again — typically a few seconds.
#
# Why a dedicated script vs. `dig-stop && dig-start`:
#   - `dig-stop` kills both API + web; `dig-start` then has to bring the
#     web dev server back up too, which loses HMR state and re-bundles.
#   - Restarting the API only means HMR-connected browsers reconnect to
#     the same web dev server they were already using.
#
# Reads + updates PIDs at ~/.config/dig/pid.json. The web entry is left
# untouched. If no PID file exists, falls back to whatever's listening on
# the configured API port.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"
USER_CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/dig"
PID_FILE="$USER_CFG_DIR/pid.json"

err() { printf '%s\n' "$*" >&2; }

PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
  err "python3 not found in PATH."
  exit 127
fi

FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

# Resolve effective config to know the API host/port for re-launch + readiness.
EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export 2>/dev/null || true)"
[[ -n "$EXPORT" ]] && eval "$EXPORT"
API_HOST="${DIG_API_HOST:-127.0.0.1}"
API_PORT="${DIG_API_PORT:-8090}"

# Logs go where dig-start put them.
LOG_DIR="${DIG_LOG_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$LOG_DIR"
API_LOG="$LOG_DIR/dig-api.log"

# ---- 1. Find the current API PID ------------------------------------------
#
# Source priority: PID file (authoritative — written by dig-start) →
# `lsof -sTCP:LISTEN` on the configured port (falls back gracefully when
# the file is missing or stale). The LISTEN filter is the same defensive
# trick dig-stop uses: without it we'd also match browsers that happen to
# have an open WebSocket to the API and kill them.

API_PID=""
if [[ -f "$PID_FILE" ]]; then
  API_PID="$("$PY" - "$PID_FILE" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    api = d.get("api")
    if api and isinstance(api, dict) and "pid" in api:
        print(api["pid"])
except Exception:
    pass
PYEOF
)"
fi

if [[ -z "$API_PID" || "$API_PID" == "None" ]] && command -v lsof >/dev/null 2>&1; then
  # IMPORTANT: -sTCP:LISTEN restricts to the listening socket only.
  # Without it, lsof also returns ESTABLISHED connections — which would
  # match every browser tab with an open WebSocket to the API and we'd
  # kill them too. Same defensive pattern as dig-stop.sh.
  API_PID="$(lsof -ti tcp:"$API_PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "$API_PID" ]]; then
  echo "[dig restart] no running API found; will start fresh."
else
  if [[ "$FORCE" -eq 1 ]]; then
    echo "[dig restart] kill -KILL $API_PID"
    kill -KILL "$API_PID" 2>/dev/null || true
  else
    echo "[dig restart] kill -TERM $API_PID (waiting up to 5s for graceful exit)"
    kill -TERM "$API_PID" 2>/dev/null || true
    for i in 1 2 3 4 5; do
      kill -0 "$API_PID" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$API_PID" 2>/dev/null; then
      echo "[dig restart] still alive; escalating to SIGKILL"
      kill -KILL "$API_PID" 2>/dev/null || true
    fi
  fi
fi

# Wait for the port to actually free up — uvicorn can take a moment to
# release the socket even after the process exits.
if command -v lsof >/dev/null 2>&1; then
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if ! lsof -ti tcp:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
  if lsof -ti tcp:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    err "[dig restart] port $API_PORT still bound after 5s — refusing to re-launch."
    err "             check 'lsof -i tcp:$API_PORT -sTCP:LISTEN' or pass --force."
    exit 3
  fi
fi

# ---- 2. Preflight + re-launch ---------------------------------------------

if [[ ! -d "$REPO_ROOT/backend/.venv" ]]; then
  err "[dig restart] backend venv missing — run ./scripts/dig-install.sh first."
  exit 1
fi

# Same launcher prefix as dig-start: setsid (linux) or nohup (mac), to
# detach from the current shell session.
START_PREFIX=()
if command -v setsid >/dev/null 2>&1; then
  START_PREFIX=(setsid)
elif command -v nohup >/dev/null 2>&1; then
  START_PREFIX=(nohup)
fi

cd "$REPO_ROOT/backend"
DIG_HOST="$API_HOST" DIG_PORT="$API_PORT" \
  "${START_PREFIX[@]}" "$REPO_ROOT/backend/.venv/bin/dig-api" \
    >> "$API_LOG" 2>&1 &
NEW_API_PID=$!

# ---- 3. Wait for /health to answer ----------------------------------------

ready=0
for i in $(seq 1 30); do
  if curl -sf "http://$API_HOST:$API_PORT/health" >/dev/null 2>&1; then
    ready=1
    echo "[dig restart] api ready (${i}s)"
    break
  fi
  sleep 1
done

if [[ "$ready" -eq 0 ]]; then
  err "[dig restart] api failed to start within 30s."
  err "             log: $API_LOG"
  exit 4
fi

# ---- 4. Update PID file (preserve web entry verbatim) ---------------------

mkdir -p "$USER_CFG_DIR"
"$PY" - "$PID_FILE" "$NEW_API_PID" "$API_PORT" "$API_LOG" <<'PYEOF'
import json, os, sys
path, api_pid, api_port, api_log = sys.argv[1:]
data = {}
if os.path.exists(path):
    try:
        data = json.load(open(path))
    except Exception:
        data = {}
data["api"] = {"pid": int(api_pid), "port": int(api_port), "log": api_log}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF

cat <<EOF

✅ API restarted.
   pid:  $NEW_API_PID
   url:  http://$API_HOST:$API_PORT
   log:  $API_LOG
EOF

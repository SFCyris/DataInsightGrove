#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Cross-platform DIG web (Next.js dev server) restart script. Works on Linux + macOS.
#
# Usage:
#   ./scripts/dig-restart-web.sh           # graceful TERM, escalate after 5s, re-launch web
#   ./scripts/dig-restart-web.sh --force   # SIGKILL the web dev server immediately, re-launch
#
# Restarts ONLY the Next.js dev server (`pnpm dev`). The backend API process
# is left running, no API consumers are interrupted. Use this when HMR gets
# wedged, postcss hangs, or `next dev` otherwise needs a kick.
#
# Why a dedicated script vs. `dig-stop && dig-start`:
#   - `dig-stop` kills both API + web; `dig-start` then has to bring the
#     API back up too, which means transient 5xx for in-flight requests.
#   - Restarting the web only means the API stays warm and any clients
#     hitting it directly are unaffected.
#
# Reads + updates PIDs at ~/.config/dig/pid.json. The api entry is left
# untouched. If no PID file exists, falls back to whatever's listening on
# the configured web port.

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
    -h|--help) sed -n '2,21p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

# Resolve effective config to know the web host/port for re-launch + readiness,
# plus the API host/port to wire into NEXT_PUBLIC_DIG_API.
EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export 2>/dev/null || true)"
[[ -n "$EXPORT" ]] && eval "$EXPORT"
API_HOST="${DIG_API_HOST:-127.0.0.1}"
API_PORT="${DIG_API_PORT:-8190}"
WEB_HOST="${DIG_WEB_HOST:-127.0.0.1}"
WEB_PORT="${DIG_WEB_PORT:-3100}"

# Logs go where dig-start put them.
LOG_DIR="${DIG_LOG_DIR:-${TMPDIR:-/tmp}}"
mkdir -p "$LOG_DIR"
WEB_LOG="$LOG_DIR/dig-web.log"

# ---- 1. Find the current web PID ------------------------------------------
#
# Source priority: PID file (authoritative — written by dig-start) →
# `lsof -sTCP:LISTEN` on the configured port (falls back gracefully when
# the file is missing or stale). The LISTEN filter is the same defensive
# trick dig-stop uses: without it we'd also match browsers that happen to
# have an open HMR WebSocket to the dev server and kill them.

WEB_PID=""
if [[ -f "$PID_FILE" ]]; then
  WEB_PID="$("$PY" - "$PID_FILE" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    web = d.get("web")
    if web and isinstance(web, dict) and "pid" in web:
        print(web["pid"])
except Exception:
    pass
PYEOF
)"
fi

if [[ -z "$WEB_PID" || "$WEB_PID" == "None" ]] && command -v lsof >/dev/null 2>&1; then
  # IMPORTANT: -sTCP:LISTEN restricts to the listening socket only.
  # Without it, lsof also returns ESTABLISHED connections — which would
  # match every browser tab with an open HMR WebSocket to the dev server
  # and we'd kill them too. Same defensive pattern as dig-stop.sh.
  WEB_PID="$(lsof -ti tcp:"$WEB_PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "$WEB_PID" ]]; then
  echo "[dig restart-web] no running web dev server found; will start fresh."
else
  if [[ "$FORCE" -eq 1 ]]; then
    echo "[dig restart-web] kill -KILL $WEB_PID"
    kill -KILL "$WEB_PID" 2>/dev/null || true
  else
    echo "[dig restart-web] kill -TERM $WEB_PID (waiting up to 5s for graceful exit)"
    kill -TERM "$WEB_PID" 2>/dev/null || true
    for i in 1 2 3 4 5; do
      kill -0 "$WEB_PID" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$WEB_PID" 2>/dev/null; then
      echo "[dig restart-web] still alive; escalating to SIGKILL"
      kill -KILL "$WEB_PID" 2>/dev/null || true
    fi
  fi
fi

# Wait for the port to actually free up — next dev can take a moment to
# release the socket even after the process exits.
if command -v lsof >/dev/null 2>&1; then
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if ! lsof -ti tcp:"$WEB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
  if lsof -ti tcp:"$WEB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    err "[dig restart-web] port $WEB_PORT still bound after 5s — refusing to re-launch."
    err "                  check 'lsof -i tcp:$WEB_PORT -sTCP:LISTEN' or pass --force."
    exit 3
  fi
fi

# ---- 2. Preflight + re-launch ---------------------------------------------

if [[ ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
  err "[dig restart-web] frontend deps missing — run 'pnpm install' from the repo root first."
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

cd "$REPO_ROOT/frontend"
NEXT_PUBLIC_DIG_API="http://$API_HOST:$API_PORT" PORT="$WEB_PORT" HOSTNAME="$WEB_HOST" \
  "${START_PREFIX[@]}" pnpm dev --port "$WEB_PORT" --hostname "$WEB_HOST" \
    >> "$WEB_LOG" 2>&1 &
NEW_WEB_PID=$!

# ---- 3. Wait for / to answer ----------------------------------------------
#
# Probe the root URL, not /health (that's API-only). The first build after a
# cold restart can take a while — give it 60s.

ready=0
for i in $(seq 1 60); do
  if curl -sf -o /dev/null "http://$WEB_HOST:$WEB_PORT/" 2>&1; then
    ready=1
    echo "[dig restart-web] web ready (${i}s)"
    break
  fi
  sleep 1
done

if [[ "$ready" -eq 0 ]]; then
  err "[dig restart-web] web failed to start within 60s."
  err "                  log: $WEB_LOG"
  exit 4
fi

# ---- 4. Update PID file (preserve api entry verbatim) ---------------------

mkdir -p "$USER_CFG_DIR"
"$PY" - "$PID_FILE" "$NEW_WEB_PID" "$WEB_PORT" "$WEB_LOG" <<'PYEOF'
import json, os, sys
path, web_pid, web_port, web_log = sys.argv[1:]
data = {}
if os.path.exists(path):
    try:
        data = json.load(open(path))
    except Exception:
        data = {}
data["web"] = {"pid": int(web_pid), "port": int(web_port), "log": web_log}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF

cat <<EOF

✅ Web dev server restarted.
   pid:  $NEW_WEB_PID
   url:  http://$WEB_HOST:$WEB_PORT
   log:  $WEB_LOG
EOF

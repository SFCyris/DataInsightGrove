#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Cross-platform DIG start script. Works on Linux + macOS.
#
# Usage:
#   ./scripts/dig-start.sh                      # detached, write PIDs, print URLs
#   ./scripts/dig-start.sh --foreground         # stay foreground, prefixed logs, Ctrl-C cleans up
#   ./scripts/dig-start.sh --local              # bind to 127.0.0.1 only (this machine)
#   ./scripts/dig-start.sh --global             # bind to 0.0.0.0 (any device on the LAN)
#   ./scripts/dig-start.sh --api-port 9000      # override API port for this run
#   ./scripts/dig-start.sh --web-port 4000      # override web port for this run
#   ./scripts/dig-start.sh --data-dir /var/dig  # override data directory
#   ./scripts/dig-start.sh --save               # persist any --*-port / --*-host / --data-dir flags to config
#
# Defaults: api 127.0.0.1:8090  · web 127.0.0.1:3000  · data <repo>/data
# Persistent overrides live at ~/.config/dig/config.json — see scripts/dig_config.py.
#
# Local vs global:
#   --local sets api.host + web.host to 127.0.0.1. DIG only answers on this
#           machine — other devices on your network can't reach it.
#   --global sets both to 0.0.0.0. Any device on your LAN can open the web UI
#           via this machine's hostname / IP. The frontend's runtime auto-
#           derives the API URL from the visiting hostname so it Just Works.
#           NOTE: DIG does not enforce auth by default — see SECURITY in the
#           startup banner.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"

# ---- portable helpers ----
err() { printf '%s\n' "$*" >&2; }

# True when the host string means "all interfaces" (`0.0.0.0`, `::`, `*`).
# Used to flip behaviour between local-only and LAN-wide modes — the
# frontend's NEXT_PUBLIC_DIG_API is pinned only in local mode so the
# browser-side `_resolveApiBase()` (window.location.hostname) takes
# over in global mode.
is_global_bind() {
  case "$1" in
    0.0.0.0|::|*"*"*) return 0 ;;
    *) return 1 ;;
  esac
}

# Enumerate every non-loopback IPv4 address on this machine. Used to
# print "open at: http://X:3000" for every interface when running in
# --global / 0.0.0.0 mode. Robust across Linux (`ip` or `hostname -I`)
# and macOS (`ifconfig`). Hostnames are added as well so users can
# bookmark the friendly form.
list_lan_addresses() {
  local addrs=()
  if command -v ip >/dev/null 2>&1; then
    while IFS= read -r ip; do
      [[ -n "$ip" && "$ip" != "127.0.0.1" ]] && addrs+=("$ip")
    done < <(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
  elif command -v ifconfig >/dev/null 2>&1; then
    while IFS= read -r ip; do
      [[ -n "$ip" && "$ip" != "127.0.0.1" ]] && addrs+=("$ip")
    done < <(ifconfig 2>/dev/null | awk '/inet [0-9]/ {print $2}')
  elif command -v hostname >/dev/null 2>&1; then
    # Linux glibc `hostname -I` lists all configured IPs, space-separated.
    for ip in $(hostname -I 2>/dev/null); do
      [[ "$ip" != "127.0.0.1" && "$ip" != "::1" ]] && addrs+=("$ip")
    done
  fi
  printf '%s\n' "${addrs[@]}"
}

# Local hostname for the friendly URL. macOS exposes this via
# `scutil --get LocalHostName` (mDNS .local form); Linux falls through
# to `hostname` which is the kernel hostname (works on any LAN with
# Avahi or just static /etc/hosts entries).
local_hostname() {
  if command -v scutil >/dev/null 2>&1; then
    local h
    h="$(scutil --get LocalHostName 2>/dev/null)"
    [[ -n "$h" ]] && { printf '%s.local\n' "$h"; return; }
  fi
  if command -v hostname >/dev/null 2>&1; then
    hostname 2>/dev/null
  fi
}

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
    --local|--localhost-only)
      # Shorthand for "--api-host 127.0.0.1 --web-host 127.0.0.1".
      CLI_API_HOST="127.0.0.1"; CLI_WEB_HOST="127.0.0.1"; shift ;;
    --global|--lan|--public)
      # Shorthand for "--api-host 0.0.0.0 --web-host 0.0.0.0".
      CLI_API_HOST="0.0.0.0"; CLI_WEB_HOST="0.0.0.0"; shift ;;
    --api-port)      CLI_API_PORT="${2:?--api-port needs a value}"; shift 2 ;;
    --web-port)      CLI_WEB_PORT="${2:?--web-port needs a value}"; shift 2 ;;
    --api-host)      CLI_API_HOST="${2:?--api-host needs a value}"; shift 2 ;;
    --web-host)      CLI_WEB_HOST="${2:?--web-host needs a value}"; shift 2 ;;
    --data-dir)      CLI_DATA_DIR="${2:?--data-dir needs a value}"; shift 2 ;;
    -h|--help)
      sed -n '2,26p' "$0" | sed 's/^# //; s/^#//'
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

# next dev — only pin NEXT_PUBLIC_DIG_API for LOCAL mode. In global mode we
# leave it unset so the frontend's runtime default ( `window.location.hostname`
# ) kicks in — that way visiting `http://10.0.0.5:3000` from a phone on the
# LAN talks to the backend at `http://10.0.0.5:8090`, not the phone's own
# localhost. See `_resolveApiBase()` in frontend/lib/api/client.ts.
cd "$REPO_ROOT/frontend"
NEXT_API_ENV=()
if ! is_global_bind "$API_HOST"; then
  NEXT_API_ENV=(NEXT_PUBLIC_DIG_API="http://$API_HOST:$API_PORT")
fi
env "${NEXT_API_ENV[@]}" PORT="$WEB_PORT" HOSTNAME="$WEB_HOST" \
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

echo
echo "✅ DIG is running."
echo

if is_global_bind "$WEB_HOST"; then
  echo "   ACCESS MODE: 🌐 LAN-wide (any device on your network can reach DIG)"
  echo
  echo "   Open the web UI at any of:"
  echo "     • http://localhost:$WEB_PORT          (this machine)"
  hn="$(local_hostname)"
  [[ -n "$hn" ]] && echo "     • http://$hn:$WEB_PORT"
  while IFS= read -r ip; do
    [[ -n "$ip" ]] && echo "     • http://$ip:$WEB_PORT"
  done < <(list_lan_addresses)
  echo
  if [[ -z "${NEXT_PUBLIC_DIG_AUTH_TOKEN:-}" ]]; then
    echo "   ⚠ SECURITY: no API auth token is set. Anyone on your network can"
    echo "     read every dataset, edit every pipeline, and trigger backend runs."
    echo "     For more than a quick demo, set NEXT_PUBLIC_DIG_AUTH_TOKEN +"
    echo "     DIG_AUTH_TOKEN, or stop the service with ./scripts/dig-stop.sh"
    echo "     and restart with --local."
    echo
  fi
else
  echo "   ACCESS MODE: 🔒 local-only (only this machine can reach DIG)"
  echo
  echo "   Open the web UI:"
  echo "     • http://localhost:$WEB_PORT"
  echo
  echo "   To make DIG reachable from other devices on your network, restart with:"
  echo "     ./scripts/dig-restart.sh --global   # this run"
  echo "     ./scripts/dig-start.sh --global --save   # remember it"
  echo
fi

echo "   api:  http://$API_HOST:$API_PORT"
echo "   pids: api=$API_PID web=$WEB_PID"
echo "   logs: $API_LOG  ·  $WEB_LOG"
echo "   stop: ./scripts/dig-stop.sh"

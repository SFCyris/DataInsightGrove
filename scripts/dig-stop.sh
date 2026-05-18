#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Cross-platform DIG stop script. Works on Linux + macOS.
#
# Usage:
#   ./scripts/dig-stop.sh           # graceful TERM, escalate to KILL after 5s
#   ./scripts/dig-stop.sh --force   # send SIGKILL immediately
#
# Reads PIDs from ~/.config/dig/pid.json (written by dig-start.sh) and falls
# back to lsof on the configured ports for any orphans the PID file missed.

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
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

# Resolve effective config to know which ports to scan as a fallback.
EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export 2>/dev/null || true)"
[[ -n "$EXPORT" ]] && eval "$EXPORT"
API_PORT="${DIG_API_PORT:-8090}"
WEB_PORT="${DIG_WEB_PORT:-3000}"

# Read recorded PIDs from the PID file (if present).
RECORDED_PIDS=""
if [[ -f "$PID_FILE" ]]; then
  RECORDED_PIDS="$("$PY" - "$PID_FILE" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    # tls_proxy is the optional third process started when TLS is enabled.
    print("\n".join(str(d[k]["pid"]) for k in ("api", "web", "tls_proxy") if k in d and isinstance(d[k], dict)))
except Exception:
    pass
PYEOF
)"
fi

stopped_any=0

if [[ -n "$RECORDED_PIDS" ]]; then
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    if kill -0 "$pid" 2>/dev/null; then
      if [[ "$FORCE" -eq 1 ]]; then
        echo "[dig stop] kill -KILL $pid"
        kill -KILL "$pid" 2>/dev/null || true
      else
        echo "[dig stop] kill -TERM $pid"
        kill -TERM "$pid" 2>/dev/null || true
      fi
      stopped_any=1
    fi
  done <<< "$RECORDED_PIDS"

  # Wait briefly for graceful shutdown, then escalate.
  if [[ "$FORCE" -ne 1 ]]; then
    for i in 1 2 3 4 5; do
      remaining=0
      while IFS= read -r pid; do
        [[ -z "$pid" ]] && continue
        if kill -0 "$pid" 2>/dev/null; then remaining=1; fi
      done <<< "$RECORDED_PIDS"
      [[ "$remaining" -eq 0 ]] && break
      sleep 1
    done
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      if kill -0 "$pid" 2>/dev/null; then
        echo "[dig stop] kill -KILL $pid (escalated)"
        kill -KILL "$pid" 2>/dev/null || true
      fi
    done <<< "$RECORDED_PIDS"
  fi
fi

# Fallback: kill anything still listening on the configured ports.
#
# IMPORTANT: -sTCP:LISTEN restricts to LISTEN-state sockets only. Without it,
# `lsof -ti tcp:3000` also returns ESTABLISHED connections — which means any
# browser tab open to http://localhost:3000 (or any other client connected to
# the API) gets its owning process killed too. We want to stop the server,
# not the user's browser.
if command -v lsof >/dev/null 2>&1; then
  # Include the HTTPS-side ports too so a TLS proxy that escaped the
  # PID kill (e.g. wrapper crashed but child kept running) gets cleaned
  # up by the orphan sweep.
  API_HTTPS_PORT="${DIG_API_HTTPS_PORT:-8443}"
  WEB_HTTPS_PORT="${DIG_WEB_HTTPS_PORT:-3443}"
  for port in "$API_PORT" "$WEB_PORT" "$API_HTTPS_PORT" "$WEB_HTTPS_PORT"; do
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      echo "[dig stop] orphan on :$port → kill $pid"
      if [[ "$FORCE" -eq 1 ]]; then
        kill -KILL "$pid" 2>/dev/null || true
      else
        kill -TERM "$pid" 2>/dev/null || true
        # brief escalation if it didn't go away
        sleep 1
        kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
      fi
      stopped_any=1
    done < <(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
  done
fi

# Clear the PID file regardless.
if [[ -f "$PID_FILE" ]]; then
  rm -f "$PID_FILE"
fi

if [[ "$stopped_any" -eq 1 ]]; then
  echo "[dig stop] done."
else
  echo "[dig stop] nothing was running."
fi

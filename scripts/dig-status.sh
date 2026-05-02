#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Print whether DIG is running and where.
#
# Source of truth for the *actual running* ports is the PID file
# (~/.config/dig/pid.json). If that doesn't exist we fall back to the
# resolved config (env + config.json + defaults) — useful before first start.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"
USER_CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/dig"
PID_FILE="$USER_CFG_DIR/pid.json"

PY="$(command -v python3 || command -v python || true)"
[[ -z "$PY" ]] && { echo "python3 not found" >&2; exit 127; }

# Defaults from config (used if the PID file is missing).
EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export 2>/dev/null || true)"
[[ -n "$EXPORT" ]] && eval "$EXPORT"
API_HOST="${DIG_API_HOST:-127.0.0.1}"
API_PORT="${DIG_API_PORT:-8090}"
WEB_HOST="${DIG_WEB_HOST:-127.0.0.1}"
WEB_PORT="${DIG_WEB_PORT:-3000}"

# If a PID file exists, prefer the ports recorded there (so status accurately
# reports the actual running services even when started with --api-port etc.).
PID_INFO=""
if [[ -f "$PID_FILE" ]]; then
  PID_INFO="$("$PY" - "$PID_FILE" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    api = d.get("api", {})
    web = d.get("web", {})
    print(f"{api.get('port','')}|{web.get('port','')}|{api.get('pid','')}|{web.get('pid','')}|{api.get('log','')}|{web.get('log','')}")
except Exception:
    pass
PYEOF
)"
  if [[ -n "$PID_INFO" ]]; then
    IFS='|' read -r api_p web_p api_pid web_pid api_log web_log <<< "$PID_INFO"
    [[ -n "$api_p" ]] && API_PORT="$api_p"
    [[ -n "$web_p" ]] && WEB_PORT="$web_p"
  fi
fi

api_alive=0
web_alive=0
curl -sf "http://$API_HOST:$API_PORT/health" >/dev/null 2>&1 && api_alive=1
curl -sf -o /dev/null "http://$WEB_HOST:$WEB_PORT/" 2>&1 && web_alive=1

api_status="❌ down"; [[ "$api_alive" -eq 1 ]] && api_status="✅ up"
web_status="❌ down"; [[ "$web_alive" -eq 1 ]] && web_status="✅ up"

cat <<EOF
DIG status
  api  $api_status   http://$API_HOST:$API_PORT
  web  $web_status   http://$WEB_HOST:$WEB_PORT
  cfg  $("$PY" "$SCRIPT_DIR/dig_config.py" path 2>/dev/null || echo '(defaults only)')
EOF

if [[ -n "${api_pid:-}" || -n "${web_pid:-}" ]]; then
  echo "  pid file: $PID_FILE"
  [[ -n "${api_pid:-}" ]] && echo "     api  pid=$api_pid  port=${api_p:-?}  log=${api_log:-?}"
  [[ -n "${web_pid:-}" ]] && echo "     web  pid=$web_pid  port=${web_p:-?}  log=${web_log:-?}"
fi

[[ "$api_alive" -eq 1 && "$web_alive" -eq 1 ]] && exit 0
exit 1

#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Linux launcher for DIG — equivalent to double-clicking the Mac app:
# starts the backend + web (if not already running), then opens the resolved
# web URL in the user's default browser.
#
# Usage:
#   linux/dig-launch.sh           # start + open in browser
#   linux/dig-launch.sh --stop    # stop everything
#
# Designed to be wired up via linux/datainsightgrove.desktop so it shows up
# in GNOME / KDE / XFCE launchers like a native app.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"

PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
  echo "python3 not found in PATH." >&2
  exit 127
fi

if [[ "${1:-}" == "--stop" ]]; then
  exec "$SCRIPT_DIR/dig-stop.sh"
fi

# Start (a no-op if already running on the same ports — exit code 2).
"$SCRIPT_DIR/dig-start.sh"
start_status=$?
if [[ "$start_status" -ne 0 && "$start_status" -ne 2 ]]; then
  exit "$start_status"
fi

# Resolve the web URL from the same config the scripts used.
EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export 2>/dev/null || true)"
[[ -n "$EXPORT" ]] && eval "$EXPORT"
WEB_HOST="${DIG_WEB_HOST:-127.0.0.1}"
WEB_PORT="${DIG_WEB_PORT:-3100}"
URL="http://$WEB_HOST:$WEB_PORT"

# xdg-open is the standard cross-desktop opener on Linux. Fall back to
# `gio open`, then `wslview` (WSL), then a literal browser binary.
open_url() {
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 &
  elif command -v gio    >/dev/null 2>&1; then gio open "$1" >/dev/null 2>&1 &
  elif command -v wslview >/dev/null 2>&1; then wslview "$1" >/dev/null 2>&1 &
  elif [[ -n "${BROWSER:-}" ]];          then "$BROWSER" "$1" >/dev/null 2>&1 &
  elif command -v firefox  >/dev/null 2>&1; then firefox "$1" >/dev/null 2>&1 &
  elif command -v chromium >/dev/null 2>&1; then chromium "$1" >/dev/null 2>&1 &
  elif command -v google-chrome >/dev/null 2>&1; then google-chrome "$1" >/dev/null 2>&1 &
  else
    echo "could not find a way to open a browser. URL: $1" >&2
    return 1
  fi
}

echo "[dig] opening $URL"
open_url "$URL"

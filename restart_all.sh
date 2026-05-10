#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# DIG — restart everything (API + Next.js dev server).
#
# Hard restart: stops both the API and the web dev server, then starts them
# back up. Browser tabs survive (the stop script's lsof fallback uses the
# `-sTCP:LISTEN` filter so client connections aren't matched), but the
# Next.js dev server losing HMR state means open browser tabs will
# auto-reconnect to a fresh dev server and re-hydrate from scratch.
#
# When you only need to bounce the API (the common case after a backend
# code change or migration), use ./scripts/dig-restart.sh instead — that
# leaves the Next dev server and HMR connections undisturbed.
#
# All args are forwarded to start.sh (port overrides, --foreground, etc.).
# stop.sh is invoked without args; if you want a forced kill, run
# `./stop.sh --force` first, then `./start.sh` directly.
#
# Examples:
#   ./restart_all.sh                      # graceful stop + restart
#   ./restart_all.sh --api-port 9000      # restart with a different API port
#   ./restart_all.sh --foreground         # stay attached after restart

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[restart_all] stopping…"
"$REPO_ROOT/scripts/dig-stop.sh"
status=$?
if [[ "$status" -ne 0 ]]; then
  echo "[restart_all] stop returned $status — continuing anyway." >&2
fi

# Brief pause so kernel has a moment to release sockets before dig-start
# does its port-conflict preflight check.
sleep 1

echo "[restart_all] starting…"
exec "$REPO_ROOT/scripts/dig-start.sh" "$@"

#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# DIG — stop everything (API + Next.js dev server).
#
# Convenience wrapper that delegates to scripts/dig-stop.sh, which:
#   - reads PIDs from ~/.config/dig/pid.json
#   - sends SIGTERM, then escalates to SIGKILL after 5 s (or immediately
#     with --force)
#   - falls back to `lsof -ti tcp:$port -sTCP:LISTEN` if the PID file is
#     missing or stale (the LISTEN filter is load-bearing — without it
#     the lsof fallback would also match browsers that have an open
#     WebSocket to the API and kill them too)
#   - clears the PID file on the way out
#
# Browser tabs are NEVER killed, regardless of flags.
#
# Examples:
#   ./stop.sh           # graceful TERM, escalate after 5 s
#   ./stop.sh --force   # SIGKILL immediately

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$REPO_ROOT/scripts/dig-stop.sh" "$@"

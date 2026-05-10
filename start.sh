#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# DIG — start everything (API + Next.js dev server).
#
# Convenience wrapper that delegates to scripts/dig-start.sh — that's the
# canonical implementation and gets the careful work (port-conflict checks,
# PID file, log file paths, readiness probes, --foreground / --save / port-
# override flags). All flags pass through unchanged. Run with --help to see
# the full menu.
#
# Examples:
#   ./start.sh                           # detached, write PIDs, print URLs
#   ./start.sh --foreground              # stay attached, prefixed logs
#   ./start.sh --api-port 9000 --save    # persist a custom API port

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$REPO_ROOT/scripts/dig-start.sh" "$@"

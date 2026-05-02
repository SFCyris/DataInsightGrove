#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# DIG — install / set up the local development environment.
#
# Convenience wrapper that delegates to scripts/dig-install.sh — that's the
# canonical implementation and gets the careful work (prereq checks,
# extras-set picking, --rebuild / --check / --jdbc handling). All flags
# pass through unchanged. Run with --help to see the full menu.
#
# Examples:
#   ./install.sh             # incremental install
#   ./install.sh --rebuild   # wipe .venv + node_modules, then reinstall
#   ./install.sh --check     # verify the environment is set up; install nothing
#   ./install.sh --jdbc      # also install the optional JDBC extras

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$REPO_ROOT/scripts/dig-install.sh" "$@"

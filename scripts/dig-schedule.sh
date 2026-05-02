#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Schedule a DIG pipeline to run on a cron schedule.
#
# Backed by the user's crontab (Linux + macOS). Each entry runs
# `dig-run.sh <pipeline> [--sample N]` so the pipeline executes via the
# already-running backend. Make sure DIG is started (or auto-starts at boot)
# for the cron entries to do anything.
#
# Usage:
#   ./scripts/dig-schedule.sh add    "*/15 * * * *" <pipeline> [--sample N]
#   ./scripts/dig-schedule.sh list
#   ./scripts/dig-schedule.sh remove <pipeline>
#
# Conventions:
#   - Each managed line in crontab is tagged with a marker:  # DIG_SCHED:<pipeline>
#   - `remove` deletes every line with the matching marker.
#   - `list` filters crontab to just the DIG-managed lines.
#
# Cross-platform: uses `crontab` which exists on every Linux + macOS install.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"
RUN_SCRIPT="$SCRIPT_DIR/dig-run.sh"

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab(1) not available — install cron or use systemd timers instead." >&2
  exit 127
fi

usage() {
  sed -n '2,19p' "$0" | sed 's/^# //; s/^#//'
  exit "${1:-0}"
}

CMD="${1:-}"
shift || true

case "$CMD" in
  list)
    crontab -l 2>/dev/null | grep "DIG_SCHED:" || echo "(no DIG schedules)"
    ;;
  add)
    SCHED="${1:?need a 5-field cron schedule, e.g. '*/15 * * * *'}"
    PIPE="${2:?need a pipeline id or unique name substring}"
    shift 2 || true
    EXTRA="$*"
    # Normalise PIPE for the marker — strip whitespace, lowercase.
    MARKER_PIPE="$(printf '%s' "$PIPE" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
    LINE="$SCHED $RUN_SCRIPT $(printf '%q' "$PIPE")"
    [[ -n "$EXTRA" ]] && LINE="$LINE $EXTRA"
    LINE="$LINE  # DIG_SCHED:$MARKER_PIPE"

    # Strip any prior entry for this pipeline so add is idempotent.
    EXISTING="$(crontab -l 2>/dev/null || true)"
    NEW="$(printf '%s\n' "$EXISTING" | grep -v "# DIG_SCHED:$MARKER_PIPE\$" || true)"
    NEW="$(printf '%s\n%s\n' "$NEW" "$LINE" | sed '/^$/d')"
    printf '%s\n' "$NEW" | crontab -
    echo "[dig-schedule] added: $LINE"
    ;;
  remove)
    PIPE="${1:?need a pipeline id or marker substring}"
    MARKER_PIPE="$(printf '%s' "$PIPE" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
    EXISTING="$(crontab -l 2>/dev/null || true)"
    NEW="$(printf '%s\n' "$EXISTING" | grep -v "# DIG_SCHED:$MARKER_PIPE" || true)"
    if [[ "$EXISTING" == "$NEW" ]]; then
      echo "[dig-schedule] no matching schedule for '$PIPE'."
      exit 1
    fi
    printf '%s\n' "$NEW" | sed '/^$/d' | crontab -
    echo "[dig-schedule] removed schedules matching '$PIPE'."
    ;;
  -h|--help|help|"") usage 0 ;;
  *) echo "unknown subcommand: $CMD" >&2; usage 64 ;;
esac

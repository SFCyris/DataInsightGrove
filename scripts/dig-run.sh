#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Run a pipeline once via the running DIG backend, then print summary.
#
# This is the script that `dig-schedule.sh` wires into cron, but it's also
# useful as a standalone CLI for ad-hoc runs.
#
# Usage:
#   ./scripts/dig-run.sh <pipeline_id_or_name> [--sample N]
#
# - <pipeline_id_or_name> may be the ULID or a unique substring of the name.
# - --sample N turns the run into a sampled preview (1 to 1_000_000 rows).
# - Exit 0 if the run succeeded, non-zero otherwise.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"

PY="$(command -v python3 || command -v python || true)"
[[ -z "$PY" ]] && { echo "python3 not found." >&2; exit 127; }

EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export 2>/dev/null || true)"
[[ -n "$EXPORT" ]] && eval "$EXPORT"
API="http://${DIG_API_HOST:-127.0.0.1}:${DIG_API_PORT:-8080}"

QUERY="${1:-}"
SAMPLE=""
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample) SAMPLE="${2:?--sample needs a value}"; shift 2 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 64 ;;
  esac
done

if [[ -z "$QUERY" ]]; then
  echo "usage: $0 <pipeline_id_or_name> [--sample N]" >&2
  exit 64
fi

if ! curl -sf "$API/health" >/dev/null 2>&1; then
  echo "api not reachable at $API — start it with ./scripts/dig-start.sh" >&2
  exit 3
fi

# Resolve query → pipeline id (substring match on name OR exact id).
PIPELINE_ID="$("$PY" - "$API" "$QUERY" <<'PYEOF'
import json, sys
from urllib.request import urlopen
api, q = sys.argv[1:]
data = json.load(urlopen(f"{api}/pipelines"))
matches = [p for p in data if p["id"] == q or q.lower() in p["name"].lower()]
if not matches:
    sys.exit(4)
if len(matches) > 1:
    print("ambiguous:", file=sys.stderr)
    for m in matches:
        print(f"  {m['id']}  {m['name']}", file=sys.stderr)
    sys.exit(5)
print(matches[0]["id"])
PYEOF
)" || { echo "no pipeline matched '$QUERY'" >&2; exit 4; }

echo "[dig-run] pipeline: $PIPELINE_ID"

BODY="{}"
[[ -n "$SAMPLE" ]] && BODY="{\"sampleRows\": $SAMPLE}"

RUN_ID="$(curl -sf -X POST "$API/pipelines/$PIPELINE_ID/runs" \
  -H 'Content-Type: application/json' -d "$BODY" \
  | "$PY" -c "import sys,json; print(json.load(sys.stdin)['id'])")" || {
    echo "could not start run." >&2
    exit 6
  }

echo "[dig-run] run started: $RUN_ID"

# Poll for completion (up to 1 hour).
for i in $(seq 1 720); do
  STATUS="$(curl -sf "$API/runs/$RUN_ID" \
    | "$PY" -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo unknown)"
  case "$STATUS" in
    succeeded)
      echo "[dig-run] succeeded ($((i * 5))s)"
      curl -sf "$API/runs/$RUN_ID" | "$PY" -m json.tool
      exit 0
      ;;
    failed)
      echo "[dig-run] failed" >&2
      curl -sf "$API/runs/$RUN_ID" | "$PY" -m json.tool >&2
      exit 1
      ;;
    queued|running)
      ;;
    *)
      echo "[dig-run] unknown status: $STATUS" >&2
      ;;
  esac
  sleep 5
done

echo "[dig-run] timeout waiting for completion." >&2
exit 7

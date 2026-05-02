#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Run backend and frontend dev servers together, with prefixed log lines and
# clean shutdown on Ctrl-C or any exit.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d backend/.venv ]]; then
  echo "backend/.venv missing — run 'make backend-setup' first." >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "frontend/node_modules missing — run 'pnpm install' from the repo root first." >&2
  exit 1
fi

# Track child PIDs and the temp pipes we set up.
PIDS=()
cleanup() {
  trap '' INT TERM
  echo
  echo "[dig dev] shutting down…"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  # Belt-and-braces: free the dev ports if anything lingered.
  lsof -ti tcp:8080 2>/dev/null | xargs -r kill 2>/dev/null || true
  lsof -ti tcp:3000 2>/dev/null | xargs -r kill 2>/dev/null || true
  wait 2>/dev/null
  echo "[dig dev] done."
}
trap cleanup INT TERM EXIT

prefix() {
  local label="$1"
  while IFS= read -r line; do
    printf "[%s] %s\n" "$label" "$line"
  done
}

# Backend (uvicorn with reload).
(
  cd backend
  DIG_RELOAD=1 .venv/bin/dig-api 2>&1 | prefix "api"
) &
PIDS+=($!)

# Frontend (next dev).
(
  cd frontend
  pnpm dev 2>&1 | prefix "web"
) &
PIDS+=($!)

echo "[dig dev] api  → http://127.0.0.1:8080  (docs: /docs)"
echo "[dig dev] web  → http://127.0.0.1:3000"
echo "[dig dev] ctrl-c to stop both."

wait

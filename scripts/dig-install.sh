#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Cross-platform DIG install script. Works on Linux + macOS.
#
# Sets up the local development environment from scratch:
#   1. Verifies prerequisites (python3 ≥ 3.11, pnpm)
#   2. Creates backend/.venv and installs the `dev` + `connectors` +
#      `visualize` + `ml` extras
#   3. Runs `pnpm install` in frontend/ (postinstall hook copies the
#      DuckDB-WASM bundles into frontend/public/duckdb-wasm/)
#   4. Reports success
#
# Usage:
#   ./scripts/dig-install.sh             # incremental — install/update what's missing
#   ./scripts/dig-install.sh --rebuild   # wipe .venv + node_modules + .next, then install
#   ./scripts/dig-install.sh --clean     # alias for --rebuild
#   ./scripts/dig-install.sh --jdbc      # also install the optional [jdbc] extra (needs CMake + JDK)
#   ./scripts/dig-install.sh --check     # only verify prereqs + that everything is installed; don't install
#
# Notes:
#   - The [jdbc] extra is opt-in because JPype1 builds from source on first
#     install and needs CMake + a JDK on PATH. Most users don't need it.
#   - The [ml] extra pulls in scikit-learn, scipy, statsmodels, etc. —
#     several hundred MB of wheels. It IS installed by default because
#     several built-in steps (k-means, PCA, forecasting) need it.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"

err()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }

REBUILD=0
CHECK_ONLY=0
WITH_JDBC=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild|--clean)  REBUILD=1; shift ;;
    --check)            CHECK_ONLY=1; shift ;;
    --jdbc)             WITH_JDBC=1; shift ;;
    -h|--help)          sed -n '2,26p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

# ---- 1. Prerequisite checks ------------------------------------------------

info "[1/4] checking prerequisites…"

# python3 ≥ 3.11
PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
  err "  ✗ python3 not on PATH. Install Python 3.11+ first."
  exit 1
fi
PY_VERSION="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%.*}"
PY_MINOR="${PY_VERSION#*.}"
if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 11 ]]; }; then
  err "  ✗ python $PY_VERSION found, but DIG needs ≥ 3.11."
  exit 1
fi
ok "  ✓ python $PY_VERSION ($PY)"

# pnpm
if ! command -v pnpm >/dev/null 2>&1; then
  err "  ✗ pnpm not on PATH. Install via: npm install -g pnpm  (or https://pnpm.io/installation)"
  exit 1
fi
PNPM_VERSION="$(pnpm --version 2>/dev/null || echo '?')"
ok "  ✓ pnpm $PNPM_VERSION ($(command -v pnpm))"

# Optional but useful: report Java if --jdbc was requested.
if [[ "$WITH_JDBC" -eq 1 ]]; then
  if command -v java >/dev/null 2>&1; then
    JAVA_VERSION="$(java -version 2>&1 | head -n1)"
    ok "  ✓ java present — $JAVA_VERSION"
  else
    warn "  ⚠ --jdbc requested but \`java\` not on PATH."
    warn "    JPype1 wheels work without a JDK at install time, but the JDBC connector"
    warn "    needs a JRE 8+ at runtime. Install one before using jdbc:// datasets."
  fi
  if ! command -v cmake >/dev/null 2>&1; then
    warn "  ⚠ cmake not on PATH — JPype1 may need to build from source."
    warn "    On macOS: brew install cmake. On Debian/Ubuntu: apt install cmake."
  fi
fi

# ---- 2. Optional rebuild — wipe everything ---------------------------------

if [[ "$REBUILD" -eq 1 && "$CHECK_ONLY" -ne 1 ]]; then
  info "[2/4] --rebuild requested — wiping previous install…"
  if [[ -d "$BACKEND_DIR/.venv" ]]; then
    rm -rf "$BACKEND_DIR/.venv"
    ok "  ✓ removed backend/.venv"
  fi
  if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    rm -rf "$FRONTEND_DIR/node_modules"
    ok "  ✓ removed frontend/node_modules"
  fi
  if [[ -d "$FRONTEND_DIR/.next" ]]; then
    rm -rf "$FRONTEND_DIR/.next"
    ok "  ✓ removed frontend/.next"
  fi
  if [[ -d "$FRONTEND_DIR/public/duckdb-wasm" ]]; then
    rm -rf "$FRONTEND_DIR/public/duckdb-wasm"
    ok "  ✓ removed frontend/public/duckdb-wasm"
  fi
fi

# ---- 3. Backend ------------------------------------------------------------

info "[3/4] backend (.venv + Python deps)…"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  if [[ -d "$BACKEND_DIR/.venv" ]]; then
    ok "  ✓ backend/.venv exists"
  else
    err "  ✗ backend/.venv missing — run without --check"
    exit 2
  fi
else
  if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
    info "  • creating backend/.venv…"
    "$PY" -m venv "$BACKEND_DIR/.venv"
  else
    info "  • backend/.venv already exists — installing/updating in place"
  fi

  # Use the venv's pip explicitly so we don't leak into the system interpreter
  # if the user happened to have backend/.venv activated externally.
  VENV_PIP="$BACKEND_DIR/.venv/bin/pip"
  EXTRAS="dev,connectors,visualize,ml"
  if [[ "$WITH_JDBC" -eq 1 ]]; then
    EXTRAS="$EXTRAS,jdbc"
  fi
  info "  • pip install -e .[$EXTRAS] (this can take a few minutes on first run)…"
  # `pip install --upgrade pip` first — modern wheels need recent resolver.
  "$VENV_PIP" install --quiet --upgrade pip
  (cd "$BACKEND_DIR" && "$VENV_PIP" install --quiet -e ".[$EXTRAS]")
  ok "  ✓ backend deps installed"
fi

# ---- 4. Frontend -----------------------------------------------------------

info "[4/4] frontend (pnpm install)…"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    ok "  ✓ frontend/node_modules exists"
  else
    err "  ✗ frontend/node_modules missing — run without --check"
    exit 2
  fi
else
  # pnpm install runs the postinstall hook which calls scripts/copy-duckdb-wasm.mjs
  # to populate frontend/public/duckdb-wasm/ — that's why we don't need to
  # copy WASM bundles ourselves here.
  info "  • pnpm install (DuckDB-WASM bundles copied via postinstall)…"
  (cd "$FRONTEND_DIR" && pnpm install --silent)
  ok "  ✓ frontend deps installed"
fi

# ---- Done ------------------------------------------------------------------

cat <<EOF

✅ DIG environment is ready.

   Next steps:
     ./start.sh                  # bring up API + web (detached)
     ./start.sh --foreground     # stay attached, prefixed logs

   Useful:
     ./scripts/dig-install.sh --check     # verify env without reinstalling
     ./scripts/dig-install.sh --rebuild   # nuke + reinstall from scratch
     ./scripts/dig-install.sh --jdbc      # also install JDBC extras
EOF

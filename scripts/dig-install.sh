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
#   ./scripts/dig-install.sh                # incremental — install/update what's missing
#   ./scripts/dig-install.sh --rebuild      # wipe .venv + node_modules + .next, then install
#   ./scripts/dig-install.sh --clean        # alias for --rebuild
#   ./scripts/dig-install.sh --jdbc         # also install the optional [jdbc] extra (needs CMake + JDK)
#   ./scripts/dig-install.sh --check        # only verify prereqs + installed state; don't install
#
# Port / host / dir overrides (persisted to ~/.config/dig/config.json,
# honored by every dig script + the Mac .app afterwards):
#   ./scripts/dig-install.sh --api-port 8090
#   ./scripts/dig-install.sh --web-port 4000
#   ./scripts/dig-install.sh --api-host 0.0.0.0
#   ./scripts/dig-install.sh --data-dir /var/dig
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
PERSIST_API_PORT=""
PERSIST_WEB_PORT=""
PERSIST_API_HOST=""
PERSIST_WEB_HOST=""
PERSIST_DATA_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild|--clean)  REBUILD=1; shift ;;
    --check)            CHECK_ONLY=1; shift ;;
    --jdbc)             WITH_JDBC=1; shift ;;
    # Port + path overrides — persisted to ~/.config/dig/config.json so
    # every script (start, stop, restart, the Mac .app, the backend's own
    # uvicorn launcher) honors them without needing the flag again.
    --api-port)  PERSIST_API_PORT="${2:?--api-port needs a value}"; shift 2 ;;
    --web-port)  PERSIST_WEB_PORT="${2:?--web-port needs a value}"; shift 2 ;;
    --api-host)  PERSIST_API_HOST="${2:?--api-host needs a value}"; shift 2 ;;
    --web-host)  PERSIST_WEB_HOST="${2:?--web-host needs a value}"; shift 2 ;;
    --data-dir)  PERSIST_DATA_DIR="${2:?--data-dir needs a value}"; shift 2 ;;
    -h|--help)          sed -n '2,33p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

# Persist any port / host / data-dir overrides BEFORE prereq checks so a
# bad install can be retried with the same effective config. dig_config.py
# is in the same directory as this script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "$PERSIST_API_PORT$PERSIST_WEB_PORT$PERSIST_API_HOST$PERSIST_WEB_HOST$PERSIST_DATA_DIR" ]]; then
  PY_FOR_CFG="$(command -v python3 || command -v python || true)"
  if [[ -n "$PY_FOR_CFG" ]]; then
    [[ -n "$PERSIST_API_PORT" ]] && "$PY_FOR_CFG" "$SCRIPT_DIR/dig_config.py" set api.port "$PERSIST_API_PORT" >/dev/null
    [[ -n "$PERSIST_WEB_PORT" ]] && "$PY_FOR_CFG" "$SCRIPT_DIR/dig_config.py" set web.port "$PERSIST_WEB_PORT" >/dev/null
    [[ -n "$PERSIST_API_HOST" ]] && "$PY_FOR_CFG" "$SCRIPT_DIR/dig_config.py" set api.host "$PERSIST_API_HOST" >/dev/null
    [[ -n "$PERSIST_WEB_HOST" ]] && "$PY_FOR_CFG" "$SCRIPT_DIR/dig_config.py" set web.host "$PERSIST_WEB_HOST" >/dev/null
    [[ -n "$PERSIST_DATA_DIR" ]] && "$PY_FOR_CFG" "$SCRIPT_DIR/dig_config.py" set dataDir "$PERSIST_DATA_DIR" >/dev/null
    info "  • persisted port/host/data-dir overrides to ~/.config/dig/config.json"
  fi
fi

# Step counter — the rebuild stage is conditional, so the numbering needs
# to reflect what's actually running rather than always showing /4 with a
# gap. Increment STEP_NO before each header.
TOTAL_STEPS=3
[[ "$REBUILD" -eq 1 && "$CHECK_ONLY" -ne 1 ]] && TOTAL_STEPS=4
STEP_NO=0
step() { STEP_NO=$((STEP_NO + 1)); info "[$STEP_NO/$TOTAL_STEPS] $*"; }

# ---- 1. Prerequisite checks ------------------------------------------------

step "checking prerequisites…"

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

# Java + cmake — required for the [jdbc] extra (JPype1 has no prebuilt wheels
# on macOS arm64 and most modern Linux, so pip falls back to building from
# source which needs both a real JDK and CMake).
#
# Subtle macOS gotcha that bit a real user: `/usr/bin/java` is a STUB shipped
# by the OS that exits with status 1 and prints "Unable to locate a Java
# Runtime" when no JDK is installed. `command -v java` succeeds against the
# stub, but every subsequent `java -version` call fails. The fix is to
# actually run `java -version` and inspect both the exit code AND the
# message text — the stub's "Unable to locate" text is the tell.
if [[ "$WITH_JDBC" -eq 1 ]]; then
  jdbc_blocked=0

  java_present=0
  if command -v java >/dev/null 2>&1; then
    JAVA_OUT="$(java -version 2>&1 || true)"
    JAVA_RC="$?"
    if [[ "$JAVA_RC" -eq 0 ]] && ! grep -qiE "Unable to locate a Java Runtime|No Java runtime present" <<< "$JAVA_OUT"; then
      JAVA_VERSION="$(printf '%s\n' "$JAVA_OUT" | head -n1)"
      ok "  ✓ java works — $JAVA_VERSION"
      java_present=1
    fi
  fi
  if [[ "$java_present" -eq 0 ]]; then
    err "  ✗ --jdbc requires a working JDK ≥ 8 on PATH."
    err "    \`java -version\` failed (or hit the macOS Java stub at /usr/bin/java)."
    case "$(uname -s)" in
      Darwin)
        err "    Install one of:"
        err "      brew install --cask temurin             # Eclipse Temurin (recommended)"
        err "      brew install openjdk@17 && sudo ln -sfn \$(brew --prefix)/opt/openjdk@17/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-17.jdk"
        ;;
      Linux)
        err "    Install one of:"
        err "      sudo apt install -y default-jdk         # Debian / Ubuntu"
        err "      sudo dnf install -y java-17-openjdk-devel  # Fedora / RHEL"
        ;;
      *)
        err "    Install a JDK 8+ for your platform and re-run."
        ;;
    esac
    jdbc_blocked=1
  fi

  if ! command -v cmake >/dev/null 2>&1; then
    err "  ✗ --jdbc requires cmake (JPype1 builds from source on macOS arm64 / modern Linux)."
    case "$(uname -s)" in
      Darwin) err "    brew install cmake" ;;
      Linux)  err "    sudo apt install -y cmake   # Debian / Ubuntu";;
      *)      err "    Install cmake for your platform and re-run." ;;
    esac
    jdbc_blocked=1
  else
    ok "  ✓ cmake $(cmake --version | head -n1 | awk '{print $3}')"
  fi

  # Apache Ant — JPype1's CMakeLists.txt does `find_program(ANT_EXECUTABLE ant)`
  # to build its embedded jar. Without Ant the cmake configure step fails
  # AFTER passing the Java + cmake checks, which is the most-frustrating
  # failure mode (you fix one prereq, re-run, hit the next). Detect early.
  if ! command -v ant >/dev/null 2>&1; then
    err "  ✗ --jdbc requires Apache Ant (JPype1's build invokes \`ant\` to compile its embedded JAR)."
    case "$(uname -s)" in
      Darwin) err "    brew install ant" ;;
      Linux)  err "    sudo apt install -y ant   # Debian / Ubuntu" ;;
      *)      err "    Install Apache Ant for your platform and re-run." ;;
    esac
    jdbc_blocked=1
  else
    ok "  ✓ ant $(ant -version 2>/dev/null | awk '{print $4}')"
  fi

  if [[ "$jdbc_blocked" -eq 1 ]]; then
    err ""
    err "  Aborting before any install runs. Re-run \`./scripts/dig-install.sh\` (without"
    err "  --jdbc) for a working core install — JDBC is opt-in and not needed for any"
    err "  built-in step."
    exit 1
  fi
fi

# ---- 2. Optional rebuild — wipe everything ---------------------------------

if [[ "$REBUILD" -eq 1 && "$CHECK_ONLY" -ne 1 ]]; then
  step "--rebuild requested — wiping previous install…"
  # Stop running services FIRST so we're not pulling node_modules out from
  # under a live `pnpm dev` (or `dig-api` uvicorn) process. Without this,
  # Next's Turbopack cache gets corrupted because the dev server holds
  # open handles to .next/dev/cache/*.sst files that our subsequent
  # rm -rf truncates — the next launch then refuses to compile and the
  # Mac app shows a blank white WKWebView. Caught the hard way.
  if [[ -x "$REPO_ROOT/scripts/dig-stop.sh" ]]; then
    info "  • stopping any running services first…"
    "$REPO_ROOT/scripts/dig-stop.sh" >/dev/null 2>&1 || true
  fi
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

step "backend (.venv + Python deps)…"

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
  # NB: `engine` and `storage` MUST be in this list — they hold polars,
  # duckdb, pyarrow, sqlalchemy, aiosqlite, alembic. Without them the API
  # process crashes on import with ModuleNotFoundError. Caught the hard way
  # when an earlier rev of this script omitted them and the dev server came
  # up but the API binary wouldn't even reach uvicorn.
  EXTRAS="engine,storage,connectors,visualize,ml,dev"
  if [[ "$WITH_JDBC" -eq 1 ]]; then
    EXTRAS="$EXTRAS,jdbc"
  fi
  info "  • pip install -e .[$EXTRAS] (this can take a few minutes on first run)…"
  # `pip install --upgrade pip` first — modern wheels need recent resolver.
  if ! "$VENV_PIP" install --quiet --upgrade pip; then
    err "  ✗ pip self-upgrade failed — see error above"
    exit 3
  fi
  # NB: explicit exit-status check — without it the surrounding script
  # (no `set -e`) would silently print "✓ backend deps installed" even
  # on a pip failure, masking real install errors. Caught the hard way
  # when a pyproject.toml typo went undetected through several rebuilds.
  if ! (cd "$BACKEND_DIR" && "$VENV_PIP" install --quiet -e ".[$EXTRAS]"); then
    err "  ✗ pip install failed — see error above"
    exit 3
  fi
  ok "  ✓ backend deps installed"
fi

# ---- 4. Frontend -----------------------------------------------------------

step "frontend (pnpm install)…"

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
  if ! (cd "$FRONTEND_DIR" && pnpm install --silent); then
    err "  ✗ pnpm install failed — see error above"
    exit 3
  fi
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

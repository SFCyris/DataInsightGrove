#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
#
# DataInsightGrove — guided installer.
#
# Run this and follow the prompts. It detects what's already on your machine,
# prints a plan, asks before installing anything, then sets DIG up end-to-end:
#
#   1. System tools          (Homebrew on macOS, Python 3.11+, pnpm)
#   2. Optional: JDBC extras (cmake + Temurin JDK + Apache Ant + jpype1)
#   3. Project dependencies  (backend/.venv + frontend/node_modules)
#   4. Optional: start DIG   (API + web UI in the background)
#
# Idempotent — re-run any time. Already-installed tools are reported as ✓
# and skipped. Designed to be run end-to-end with no documentation needed.
#
# Flags (all optional — interactive mode is the default):
#   -y, --yes               Accept the recommended defaults at every prompt
#   --jdbc                  Pre-answer "yes" to "install JDBC support?"
#   --no-jdbc               Pre-answer "no" to "install JDBC support?"
#   --no-start              Don't ask about starting; finish after install
#   --rebuild               Pass --rebuild to the project installer (nuke .venv)
#   --non-interactive       Equivalent to -y --no-start
#   -h, --help              Print this header and exit
#
# Power users / CI: see scripts/dig-bootstrap.sh and scripts/dig-install.sh
# for the same operations split into separate primitives.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"

# ---------- pretty output -------------------------------------------------
# tput-based colors degrade gracefully when stdout isn't a TTY (CI logs,
# redirected output) so we don't dump escape codes into log files.
if [[ -t 1 ]] && command -v tput >/dev/null 2>&1; then
  C_RED="$(tput setaf 1)"; C_GREEN="$(tput setaf 2)"; C_YELLOW="$(tput setaf 3)"
  C_BLUE="$(tput setaf 4)"; C_MAG="$(tput setaf 5)"; C_CYAN="$(tput setaf 6)"
  C_DIM="$(tput dim)"; C_BOLD="$(tput bold)"; C_RESET="$(tput sgr0)"
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_MAG=""; C_CYAN=""
  C_DIM=""; C_BOLD=""; C_RESET=""
fi

err()    { printf '%s%s%s\n' "$C_RED" "$*" "$C_RESET" >&2; }
warn()   { printf '%s%s%s\n' "$C_YELLOW" "$*" "$C_RESET" >&2; }
ok()     { printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
miss()   { printf '%s✗%s %s\n' "$C_RED"   "$C_RESET" "$*"; }
info()   { printf '%s%s%s\n' "$C_CYAN" "$*" "$C_RESET"; }
hdr()    { printf '\n%s%s%s%s\n' "$C_BOLD" "$C_MAG" "$*" "$C_RESET"; }
muted()  { printf '%s%s%s\n' "$C_DIM" "$*" "$C_RESET"; }

banner() {
  printf '\n'
  printf '%s%s🌳 DataInsightGrove — guided installer%s\n' "$C_BOLD" "$C_GREEN" "$C_RESET"
  printf '%s   Detects what you have, asks before installing anything, finishes with DIG running.%s\n' "$C_DIM" "$C_RESET"
  printf '\n'
}

# ---------- flag parsing --------------------------------------------------
ASSUME_YES=0
JDBC_PREF=""        # "" = ask, "yes", "no"
START_PREF=""       # "" = ask, "yes", "no"
ACCESS_PREF=""      # "" = ask, "local", "global"
REBUILD_FLAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)            ASSUME_YES=1; shift ;;
    --jdbc)              JDBC_PREF="yes"; shift ;;
    --no-jdbc)           JDBC_PREF="no"; shift ;;
    --local)             ACCESS_PREF="local"; shift ;;
    --global|--lan)      ACCESS_PREF="global"; shift ;;
    --no-start)          START_PREF="no"; shift ;;
    --rebuild)           REBUILD_FLAG="--rebuild"; shift ;;
    --non-interactive)   ASSUME_YES=1; START_PREF="no"; shift ;;
    -h|--help)           sed -n '2,30p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) err "unknown flag: $1"; err "Run with --help to see options."; exit 64 ;;
  esac
done

# ---------- prompt helper -------------------------------------------------
# `ask "question" default` returns 0 if the user answered yes, 1 otherwise.
# Default is "y" or "n" — used both as the visible hint and as the answer
# when the user just hits enter (or when --yes is passed).
ask() {
  local prompt="$1" default="$2"
  local hint="[Y/n]"; [[ "$default" == "n" ]] && hint="[y/N]"
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    [[ "$default" == "y" ]] && return 0 || return 1
  fi
  printf '%s%s%s %s ' "$C_BOLD" "$prompt" "$C_RESET" "$hint"
  read -r ans
  [[ -z "$ans" ]] && ans="$default"
  [[ "$ans" =~ ^[Yy] ]]
}

# ---------- detect platform ----------------------------------------------
OS="$(uname -s)"
DISTRO_LABEL=""
if [[ "$OS" == "Linux" ]] && [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  DISTRO_LABEL="${PRETTY_NAME:-${ID:-Linux}}"
fi
case "$OS" in
  Darwin) PLATFORM="macOS" ;;
  Linux)
    if   command -v apt-get >/dev/null 2>&1; then PLATFORM="Linux (apt-get)"
    elif command -v dnf     >/dev/null 2>&1; then PLATFORM="Linux (dnf)"
    elif command -v yum     >/dev/null 2>&1; then PLATFORM="Linux (yum)"
    elif command -v pacman  >/dev/null 2>&1; then PLATFORM="Linux (pacman)"
    elif command -v zypper  >/dev/null 2>&1; then PLATFORM="Linux (zypper)"
    else                                          PLATFORM="Linux (unknown)"; fi
    [[ -n "$DISTRO_LABEL" ]] && PLATFORM="$DISTRO_LABEL — $PLATFORM"
    ;;
  *) PLATFORM="$OS (unsupported)" ;;
esac

# ---------- environment scan ---------------------------------------------
BREW_OK=0; PYTHON_OK=0; PNPM_OK=0
CMAKE_OK=0; JAVA_OK=0; ANT_OK=0
VENV_OK=0; NODE_MODULES_OK=0

check_brew() {
  [[ "$OS" != "Darwin" ]] && return
  if command -v brew >/dev/null 2>&1; then
    ok "Homebrew $(brew --version 2>/dev/null | head -n1 | awk '{print $2}')"
    BREW_OK=1
  else
    miss "Homebrew — not installed"
    muted "    Required on macOS for installing python / pnpm / cmake / JDK / ant"
  fi
}

check_python() {
  local PY
  PY="$(command -v python3 || command -v python || true)"
  if [[ -z "$PY" ]]; then
    miss "Python 3.11+ — not installed"
    return
  fi
  local PV PMA PMI
  PV="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 0.0)"
  PMA="${PV%.*}"; PMI="${PV#*.}"
  if [[ "$PMA" -ge 3 && "$PMI" -ge 11 ]]; then
    ok "Python $PV ($PY)"
    PYTHON_OK=1
  else
    miss "Python $PV — too old (need ≥ 3.11)"
  fi
}

check_pnpm() {
  if command -v pnpm >/dev/null 2>&1; then
    ok "pnpm $(pnpm --version)"
    PNPM_OK=1
  else
    miss "pnpm — not installed"
  fi
}

check_cmake() {
  if command -v cmake >/dev/null 2>&1; then
    ok "cmake $(cmake --version | head -n1 | awk '{print $3}')"
    CMAKE_OK=1
  else
    miss "cmake — not installed (only needed for JDBC support)"
  fi
}

check_java() {
  # macOS ships a stub at /usr/bin/java that exits 1 with "Unable to locate
  # a Java Runtime" when no JDK is installed. `command -v` returns success
  # against the stub, so the only reliable test is to run `java -version`
  # and inspect both the exit code AND the message text.
  if ! command -v java >/dev/null 2>&1; then
    miss "Java — not installed (only needed for JDBC support)"
    return
  fi
  local OUT RC
  OUT="$(java -version 2>&1 || true)"; RC="$?"
  if [[ "$RC" -eq 0 ]] && ! grep -qiE "Unable to locate a Java Runtime|No Java runtime present" <<< "$OUT"; then
    ok "Java works — $(printf '%s\n' "$OUT" | head -n1)"
    JAVA_OK=1
  else
    miss "Java — \`java -version\` failed (only needed for JDBC support)"
    muted "    macOS Java stub at /usr/bin/java — install a real JDK to use it"
  fi
}

check_ant() {
  if command -v ant >/dev/null 2>&1; then
    ok "Apache Ant $(ant -version 2>/dev/null | awk '{print $4}')"
    ANT_OK=1
  else
    miss "Apache Ant — not installed (only needed for JDBC support; jpype1 build)"
  fi
}

check_project_deps() {
  if [[ -d "$REPO_ROOT/backend/.venv" ]]; then
    ok "backend/.venv exists"
    VENV_OK=1
  else
    miss "backend/.venv — not yet created"
  fi
  if [[ -d "$REPO_ROOT/frontend/node_modules" ]]; then
    ok "frontend/node_modules exists"
    NODE_MODULES_OK=1
  else
    miss "frontend/node_modules — not yet installed"
  fi
}

# ---------- run scan ------------------------------------------------------
banner

hdr "🔎  Step 1 of 5 — checking what's already on your system"
muted "Platform: $PLATFORM"
echo
muted "Required (always):"
check_brew
check_python
check_pnpm

echo
muted "Optional — only needed if you'll connect to JDBC databases (Oracle, MS SQL, etc.):"
check_cmake
check_java
check_ant

echo
muted "Project dependencies:"
check_project_deps

# ---------- decide what needs doing --------------------------------------
NEEDS_BREW=0
[[ "$BREW_OK" -eq 0 && "$OS" == "Darwin" ]] && NEEDS_BREW=1
NEEDS_PYTHON=$(( PYTHON_OK == 0 ? 1 : 0 ))
NEEDS_PNPM=$(( PNPM_OK == 0 ? 1 : 0 ))

NEEDS_PROJECT=0
[[ "$VENV_OK" -eq 0 || "$NODE_MODULES_OK" -eq 0 ]] && NEEDS_PROJECT=1
[[ -n "$REBUILD_FLAG" ]] && NEEDS_PROJECT=1

NEEDS_SYSTEM_CORE=0
[[ "$NEEDS_BREW" -eq 1 || "$NEEDS_PYTHON" -eq 1 || "$NEEDS_PNPM" -eq 1 ]] && NEEDS_SYSTEM_CORE=1

# JDBC: the user can choose. If they choose yes, we may also need Java/cmake/ant.
WANT_JDBC=0
case "$JDBC_PREF" in
  yes) WANT_JDBC=1 ;;
  no)  WANT_JDBC=0 ;;
  "")
    hdr "🔌  Step 2 of 5 — optional: JDBC database connector"
    cat <<EOF
The JDBC connector lets DIG read from Oracle, SQL Server, DB2, Sybase, etc.
via JDBC drivers. It's NOT needed for any built-in step or for CSV /
Parquet / Postgres / MySQL / SQLite / DuckDB workflows.

Cost of installing:
  • ~150 MB more disk
  • Pulls in cmake, OpenJDK (Temurin via Homebrew on macOS), Apache Ant
  • First install builds jpype1 from source (a couple of minutes)

EOF
    if ask "Install the JDBC connector?" "n"; then
      WANT_JDBC=1
    else
      WANT_JDBC=0
    fi
    ;;
esac

NEEDS_JDBC_TOOLS=0
if [[ "$WANT_JDBC" -eq 1 ]]; then
  if [[ "$CMAKE_OK" -eq 0 || "$JAVA_OK" -eq 0 || "$ANT_OK" -eq 0 ]]; then
    NEEDS_JDBC_TOOLS=1
  fi
fi

# ---- access mode prompt -------------------------------------------------
# Whether DIG should listen on 127.0.0.1 only (local) or 0.0.0.0 (LAN-wide).
# Persisted via dig-install.sh's --api-host / --web-host flags so every
# subsequent ./start.sh / ./scripts/dig-restart.sh honors it without the
# user having to remember.
case "$ACCESS_PREF" in
  local|global) ;;
  "")
    # --yes / --non-interactive should default to LOCAL — the safe
    # choice. Surfacing global mode requires an explicit choice from a
    # human at the prompt.
    if [[ "$ASSUME_YES" -eq 1 ]]; then
      ACCESS_PREF="local"
    else
    hdr "🌐  Step 2b of 5 — network access"
    cat <<EOF
Should DIG be reachable only from this machine, or from any device on
your local network (phone, laptop, another computer)?

  • LOCAL (default)  Only this computer. The web UI lives at
                     http://localhost:3000 and nothing else can talk to it.
                     Best for personal use and the safest default.

  • LAN-wide         Any device on your home / office network can reach
                     DIG via this machine's IP. Useful for demos, sharing
                     a pipeline mid-flight, or running on a small server.
                     ⚠ DIG does NOT enforce auth by default — anyone on
                     the LAN who reaches the URL gets full editor access.

You can flip this any time with:
    ./scripts/dig-restart.sh --local   |   --global

EOF
    if ask "Make DIG reachable from other devices on your network?" "n"; then
      ACCESS_PREF="global"
    else
      ACCESS_PREF="local"
    fi
    fi  # close the ASSUME_YES branch
    ;;
esac
case "$ACCESS_PREF" in
  local)  PERSIST_HOST="127.0.0.1" ;;
  global) PERSIST_HOST="0.0.0.0" ;;
esac

# ---------- print plan ---------------------------------------------------
hdr "📋  Step 3 of 5 — plan"
plan_lines=()
[[ "$NEEDS_BREW"   -eq 1 ]] && plan_lines+=("install Homebrew")
[[ "$NEEDS_PYTHON" -eq 1 ]] && plan_lines+=("install Python 3.11")
[[ "$NEEDS_PNPM"   -eq 1 ]] && plan_lines+=("install pnpm")
if [[ "$WANT_JDBC" -eq 1 ]]; then
  [[ "$CMAKE_OK" -eq 0 ]] && plan_lines+=("install cmake")
  [[ "$JAVA_OK"  -eq 0 ]] && plan_lines+=("install OpenJDK (Temurin)")
  [[ "$ANT_OK"   -eq 0 ]] && plan_lines+=("install Apache Ant")
fi
[[ "$NEEDS_PROJECT" -eq 1 ]] && plan_lines+=("create backend/.venv + run pnpm install (project deps)")
if [[ "$WANT_JDBC" -eq 1 ]]; then
  plan_lines+=("install jpype1 (JDBC bridge — builds from source)")
fi

if [[ "${#plan_lines[@]}" -eq 0 ]]; then
  ok "Nothing to do — everything is already in place."
  echo
else
  for ln in "${plan_lines[@]}"; do
    printf '   • %s\n' "$ln"
  done
  echo
  if ! ask "Proceed with the plan above?" "y"; then
    info "OK — exiting without changes."
    exit 0
  fi
fi

# ---------- execute -------------------------------------------------------
hdr "🛠  Step 4 of 5 — installing"

# (a) System tools — delegate to dig-bootstrap.sh, which handles brew,
# python, pnpm, plus the JDBC trio (cmake/jdk/ant) when --jdbc is passed.
# This is the single source of truth for OS-package decisions.
if [[ "$NEEDS_SYSTEM_CORE" -eq 1 || "$NEEDS_JDBC_TOOLS" -eq 1 ]]; then
  bootstrap_args=()
  [[ "$WANT_JDBC" -eq 1 ]] && bootstrap_args+=(--jdbc)

  info "→ Running ./scripts/dig-bootstrap.sh ${bootstrap_args[*]}"
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    # Bootstrap's only interactive prompt is the Homebrew install
    # confirmation. With -y we accept it via `yes y` piping.
    if ! yes y | "$SCRIPT_DIR/dig-bootstrap.sh" "${bootstrap_args[@]}"; then
      err "✗ system bootstrap failed — see error above"
      exit 2
    fi
  else
    if ! "$SCRIPT_DIR/dig-bootstrap.sh" "${bootstrap_args[@]}"; then
      err "✗ system bootstrap failed — see error above"
      exit 2
    fi
  fi
  echo
fi

# (b) Project dependencies — delegate to dig-install.sh. Pass the access-
# mode choice via --api-host / --web-host so dig-install persists it to
# ~/.config/dig/config.json (its persistence step runs BEFORE prereq
# checks, so the values stick even when --check would have early-exited).
if [[ "$NEEDS_PROJECT" -eq 1 || "$WANT_JDBC" -eq 1 || -n "${PERSIST_HOST:-}" ]]; then
  install_args=()
  [[ -n "$REBUILD_FLAG" ]] && install_args+=("$REBUILD_FLAG")
  [[ "$WANT_JDBC" -eq 1 ]] && install_args+=(--jdbc)
  if [[ -n "${PERSIST_HOST:-}" ]]; then
    install_args+=(--api-host "$PERSIST_HOST" --web-host "$PERSIST_HOST")
  fi
  # When NOTHING needs (re)installing but we DO need to persist the host
  # choice, run with --check so dig-install just records the values and
  # exits without re-doing the venv. The --check path still runs the
  # config-persistence block at the top of dig-install.sh.
  if [[ "$NEEDS_PROJECT" -eq 0 && "$WANT_JDBC" -eq 0 ]]; then
    install_args+=(--check)
  fi

  info "→ Running ./scripts/dig-install.sh ${install_args[*]}"
  if ! "$SCRIPT_DIR/dig-install.sh" "${install_args[@]}"; then
    err "✗ project install failed — see error above"
    exit 3
  fi
fi

# ---------- offer to start ------------------------------------------------
hdr "🚀  Step 5 of 5 — start DIG"

START_NOW=0
case "$START_PREF" in
  no)  START_NOW=0 ;;
  yes) START_NOW=1 ;;
  "")
    if [[ "$ASSUME_YES" -eq 1 ]]; then
      START_NOW=0  # never auto-start a long-running daemon under -y
    elif ask "Start DIG now? (API + web UI, detached)" "y"; then
      START_NOW=1
    fi
    ;;
esac

if [[ "$START_NOW" -eq 1 ]]; then
  info "→ Running ./start.sh"
  if "$REPO_ROOT/start.sh"; then
    echo
    ok "DIG is running."
    echo
    info "Open http://localhost:3000 in your browser."
    info "Use ./stop.sh to shut it down."
  else
    err "✗ start failed — see error above"
    exit 4
  fi
else
  echo
  ok "Setup complete."
  echo
  info "When you're ready to use DIG:"
  echo "    ./start.sh                 # start the API + web UI"
  echo "    Open http://localhost:3000"
  echo "    ./stop.sh                  # stop everything"
fi

echo
muted "Re-run ./install.sh any time to verify or repair your environment."

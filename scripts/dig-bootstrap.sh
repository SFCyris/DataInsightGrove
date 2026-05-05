#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
#
# Bootstrap a vanilla macOS or Linux box for DataInsightGrove development.
# Installs the SYSTEM-LEVEL prerequisites that `dig-install.sh` then assumes:
#
#   Always:           Homebrew (macOS only), Python 3.11+, pnpm
#   With --jdbc:      cmake, OpenJDK (Temurin via brew on macOS), Apache Ant
#
# Usage:
#   ./scripts/dig-bootstrap.sh                     # core: brew + python + pnpm
#   ./scripts/dig-bootstrap.sh --jdbc              # ALSO: cmake + temurin + ant
#   ./scripts/dig-bootstrap.sh --dry-run           # print what would happen, change nothing
#   ./scripts/dig-bootstrap.sh --jdbc --dry-run    # combine
#
# After bootstrap, run `./scripts/dig-install.sh` (add --jdbc if you bootstrapped --jdbc).
#
# Design notes:
#   - Idempotent: if a tool is already present and recent enough, it's skipped.
#   - Asks for confirmation before installing Homebrew itself (interactive,
#     wants sudo). After that, brew installs are unattended.
#   - On Linux, prefers apt > dnf > pacman based on what's on PATH; refuses
#     gracefully on unknown distros and prints what to install manually.
#   - Does NOT touch backend/.venv or frontend/node_modules — that's
#     dig-install.sh's job. Bootstrap is the system-tool layer only.

set -u

err()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }

WITH_JDBC=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --jdbc)    WITH_JDBC=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,29p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

OS="$(uname -s)"

# ---- run-or-print helper --------------------------------------------------
# Wraps each install command in a single place so --dry-run actually means
# "print the exact commands that would run". Without this the script and
# the dry-run output drift over time.
run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '  \033[2m$ %s\033[0m\n' "$*"
  else
    info "  $ $*"
    eval "$@"
  fi
}

confirm() {
  local prompt="$1"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '  \033[2m[would prompt: %s]\033[0m\n' "$prompt"
    return 0
  fi
  read -r -p "$prompt [y/N] " ans
  [[ "$ans" =~ ^[Yy] ]]
}

# ---- detect platform-specific package manager -----------------------------
PKG_MGR=""
case "$OS" in
  Darwin) PKG_MGR="brew" ;;
  Linux)
    if   command -v apt    >/dev/null 2>&1; then PKG_MGR="apt"
    elif command -v dnf    >/dev/null 2>&1; then PKG_MGR="dnf"
    elif command -v pacman >/dev/null 2>&1; then PKG_MGR="pacman"
    else
      err "Unknown Linux distro — no apt/dnf/pacman on PATH."
      err "Install the dependencies listed below manually, then run dig-install.sh."
      err "  Required: python3 (>=3.11), pnpm"
      [[ "$WITH_JDBC" -eq 1 ]] && err "  --jdbc adds: cmake, default-jdk, ant"
      exit 1
    fi
    ;;
  *)
    err "Unsupported platform: $OS"
    err "  Bootstrap supports macOS (Darwin) and Linux only."
    err "  On Windows, use WSL2 + Ubuntu and run this script inside it."
    exit 1
    ;;
esac

info "=== DIG bootstrap on $OS ($PKG_MGR) ==="
[[ "$DRY_RUN" -eq 1 ]] && warn "(dry-run mode -- nothing will be installed)"

# ---- 1. Homebrew (macOS only) --------------------------------------------
if [[ "$OS" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1; then
    ok "OK Homebrew $(brew --version 2>/dev/null | head -n1 | awk '{print $2}')"
  else
    warn "Homebrew is not installed. It's required for installing python/pnpm/cmake/openjdk/ant."
    warn "The official installer needs sudo and downloads ~50MB."
    if confirm "Install Homebrew now?"; then
      run '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
      # Add brew to PATH for the rest of this script (Apple Silicon path).
      if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
      elif [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
      fi
    else
      err "Bootstrap aborted -- Homebrew is required on macOS."
      err "After installing it manually, re-run this script."
      exit 1
    fi
  fi
fi

# ---- 2. Python 3.11+ -----------------------------------------------------
PY="$(command -v python3 || command -v python || true)"
NEED_PY=1
if [[ -n "$PY" ]]; then
  PV="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 0.0)"
  PMA="${PV%.*}"; PMI="${PV#*.}"
  if [[ "$PMA" -ge 3 && "$PMI" -ge 11 ]]; then
    ok "OK python $PV ($PY)"
    NEED_PY=0
  else
    warn "python $PV is too old (need >= 3.11)"
  fi
fi
if [[ "$NEED_PY" -eq 1 ]]; then
  case "$PKG_MGR" in
    brew)   run "brew install python@3.11" ;;
    apt)    run "sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip" ;;
    dnf)    run "sudo dnf install -y python3.11" ;;
    pacman) run "sudo pacman -S --noconfirm python" ;;
  esac
fi

# ---- 3. pnpm -------------------------------------------------------------
if command -v pnpm >/dev/null 2>&1; then
  ok "OK pnpm $(pnpm --version)"
else
  case "$PKG_MGR" in
    brew)   run "brew install pnpm" ;;
    apt)    run "curl -fsSL https://get.pnpm.io/install.sh | sh -" ;;
    dnf)    run "curl -fsSL https://get.pnpm.io/install.sh | sh -" ;;
    pacman) run "sudo pacman -S --noconfirm pnpm" ;;
  esac
fi

# ---- 4. JDBC extras: cmake + JDK + ant -----------------------------------
if [[ "$WITH_JDBC" -eq 1 ]]; then
  info "=== --jdbc: cmake + JDK + ant ==="

  if command -v cmake >/dev/null 2>&1; then
    ok "OK cmake $(cmake --version | head -n1 | awk '{print $3}')"
  else
    case "$PKG_MGR" in
      brew)   run "brew install cmake" ;;
      apt)    run "sudo apt install -y cmake" ;;
      dnf)    run "sudo dnf install -y cmake" ;;
      pacman) run "sudo pacman -S --noconfirm cmake" ;;
    esac
  fi

  # Java: detect, but ONLY trust the binary if `java -version` exits 0 AND
  # doesn't print the macOS stub's "Unable to locate" message. Same logic
  # as dig-install.sh.
  java_ok=0
  if command -v java >/dev/null 2>&1; then
    JOUT="$(java -version 2>&1 || true)"
    JRC="$?"
    if [[ "$JRC" -eq 0 ]] && ! grep -qiE "Unable to locate a Java Runtime|No Java runtime present" <<< "$JOUT"; then
      ok "OK java works -- $(printf '%s\n' "$JOUT" | head -n1)"
      java_ok=1
    fi
  fi
  if [[ "$java_ok" -eq 0 ]]; then
    case "$PKG_MGR" in
      brew)   run "brew install --cask temurin" ;;
      apt)    run "sudo apt install -y default-jdk" ;;
      dnf)    run "sudo dnf install -y java-17-openjdk-devel" ;;
      pacman) run "sudo pacman -S --noconfirm jdk-openjdk" ;;
    esac
  fi

  if command -v ant >/dev/null 2>&1; then
    ok "OK ant $(ant -version 2>/dev/null | awk '{print $4}')"
  else
    case "$PKG_MGR" in
      brew)   run "brew install ant" ;;
      apt)    run "sudo apt install -y ant" ;;
      dnf)    run "sudo dnf install -y ant" ;;
      pacman) run "sudo pacman -S --noconfirm apache-ant" ;;
    esac
  fi
fi

# ---- 5. Done -------------------------------------------------------------
echo
if [[ "$DRY_RUN" -eq 1 ]]; then
  ok "Dry run complete. Re-run without --dry-run to actually install."
else
  ok "System bootstrap complete."
  echo
  info "Next: run the project installer to set up the .venv + node_modules:"
  if [[ "$WITH_JDBC" -eq 1 ]]; then
    echo "    ./scripts/dig-install.sh --jdbc"
  else
    echo "    ./scripts/dig-install.sh"
  fi
  echo
  info "Then start the stack:"
  echo "    ./start.sh"
fi

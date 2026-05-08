#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
#
# Bootstrap a vanilla macOS or Linux box for DataInsightGrove development.
# Installs the SYSTEM-LEVEL prerequisites that `dig-install.sh` then assumes:
#
#   Always:           Homebrew (macOS only), Python 3.11+, pnpm,
#                     plus base-build (gcc/make/python-headers) on Linux.
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
# Distro support:
#   • macOS (Homebrew)             — primary
#   • Debian / Ubuntu (apt-get)    — Debian 12+, Ubuntu 22.04+ (auto-uses
#                                    deadsnakes PPA on 22.04 since the
#                                    default python3 is 3.10).
#   • Fedora / RHEL / Rocky / Alma — dnf preferred, falls back to yum on
#                                    RHEL 7-style hosts.
#   • Arch / Manjaro (pacman)      — assumes recent base-devel.
#
# Design notes:
#   - Idempotent: if a tool is already present and recent enough, it's skipped.
#   - Asks for confirmation before installing Homebrew itself (interactive,
#     wants sudo). After that, brew installs are unattended.
#   - On Linux, prefers apt > dnf > yum > pacman based on what's on PATH;
#     refuses gracefully on unknown distros and prints what to install
#     manually.
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
    -h|--help) sed -n '2,38p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
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
DISTRO_ID=""        # "debian", "ubuntu", "fedora", "rhel", "rocky", "almalinux", …
DISTRO_VERSION=""   # "12", "22.04", "9", …
case "$OS" in
  Darwin) PKG_MGR="brew" ;;
  Linux)
    # /etc/os-release is the standard cross-distro source of truth — every
    # systemd distro ships it (Debian 8+, Ubuntu 16.04+, Fedora 18+,
    # RHEL 7+, Arch). Fall back to PATH probes for the rare host without
    # it.
    if [[ -r /etc/os-release ]]; then
      # shellcheck disable=SC1091
      . /etc/os-release
      DISTRO_ID="${ID:-}"
      DISTRO_VERSION="${VERSION_ID:-}"
    fi
    if   command -v apt-get >/dev/null 2>&1; then PKG_MGR="apt"
    elif command -v dnf     >/dev/null 2>&1; then PKG_MGR="dnf"
    elif command -v yum     >/dev/null 2>&1; then PKG_MGR="yum"
    elif command -v pacman  >/dev/null 2>&1; then PKG_MGR="pacman"
    elif command -v zypper  >/dev/null 2>&1; then PKG_MGR="zypper"
    else
      err "Unknown Linux distro — no apt-get/dnf/yum/pacman/zypper on PATH."
      err "Install the dependencies listed below manually, then run dig-install.sh."
      err "  Required: python3 (>=3.11), pnpm, gcc, make, python3-dev/devel, curl, ca-certificates"
      [[ "$WITH_JDBC" -eq 1 ]] && err "  --jdbc adds: cmake, default-jdk / java-17-openjdk-devel, ant"
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

PLATFORM_DESC="$OS"
[[ -n "$DISTRO_ID" ]] && PLATFORM_DESC="$DISTRO_ID $DISTRO_VERSION ($PKG_MGR)"
[[ "$OS" == "Darwin" ]] && PLATFORM_DESC="macOS ($PKG_MGR)"

info "=== DIG bootstrap on $PLATFORM_DESC ==="
[[ "$DRY_RUN" -eq 1 ]] && warn "(dry-run mode -- nothing will be installed)"

# ---- 0. Linux base packages ---------------------------------------------
# pip needs gcc + python headers to build polars / pyarrow / numpy from
# source when no prebuilt wheel matches; the pnpm install-script needs
# curl + ca-certificates; HTTPS to PyPI needs ca-certificates. On a
# minimal Debian/Ubuntu Server or a freshly-pulled fedora-minimal image,
# none of these are present. Install ONCE upfront — much friendlier than
# the user hitting "gcc not found" mid-pip-install three minutes in.
linux_base_packages() {
  case "$PKG_MGR" in
    apt)
      # `apt-get` over `apt`: apt prints "WARNING: apt does not have a
      # stable CLI interface" on stderr in scripted use. apt-get is
      # the documented scripting interface.
      run "sudo apt-get update -qq"
      run "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
           ca-certificates curl gnupg unzip pkg-config build-essential"
      ;;
    dnf)
      # @development-tools is the meta-group covering gcc/make/binutils.
      # Newer dnf5 prefers `dnf group install` syntax; both forms work
      # back to RHEL 8.
      run "sudo dnf install -y ca-certificates curl gnupg2 unzip pkgconf-pkg-config"
      run "sudo dnf group install -y development-tools || sudo dnf groupinstall -y 'Development Tools'"
      ;;
    yum)
      # RHEL/CentOS 7 path. Same coverage as dnf.
      run "sudo yum install -y ca-certificates curl gnupg2 unzip pkgconfig"
      run "sudo yum groupinstall -y 'Development Tools'"
      ;;
    pacman)
      # base-devel is Arch's equivalent of build-essential (gcc, make, …).
      # Pacman's --needed skips already-installed packages cleanly.
      run "sudo pacman -Sy --noconfirm --needed base-devel ca-certificates curl unzip"
      ;;
    zypper)
      run "sudo zypper --non-interactive install -y ca-certificates curl unzip pkg-config"
      run "sudo zypper --non-interactive install -y --type pattern devel_basis"
      ;;
  esac
}
if [[ "$OS" == "Linux" ]]; then
  info "--- Linux base packages (gcc/make + curl + headers) ---"
  linux_base_packages
fi

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
# Probe a list of likely python interpreter names; pick the first one whose
# (major.minor) is ≥ 3.11. This handles Fedora 40 (`python3` = 3.12),
# Ubuntu 24.04 (`python3` = 3.12), Debian 12 (`python3` = 3.11), and the
# explicit `python3.11` on RHEL 9 / Ubuntu 22.04 + deadsnakes — all
# without requiring the user to know which one is installed.
detect_python() {
  local py pv pma pmi
  for py in python3.13 python3.12 python3.11 python3 python; do
    py="$(command -v "$py" 2>/dev/null || true)"
    [[ -z "$py" ]] && continue
    pv="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 0.0)"
    pma="${pv%.*}"; pmi="${pv#*.}"
    if [[ "$pma" -ge 3 && "$pmi" -ge 11 ]]; then
      printf '%s\t%s\n' "$py" "$pv"
      return 0
    fi
  done
  return 1
}

PY_INFO="$(detect_python || true)"
if [[ -n "$PY_INFO" ]]; then
  ok "OK python $(printf '%s\n' "$PY_INFO" | cut -f2) ($(printf '%s\n' "$PY_INFO" | cut -f1))"
else
  case "$PKG_MGR" in
    brew)
      run "brew install python@3.11"
      ;;
    apt)
      # Ubuntu 22.04 ships python3.10 by default — install python3.11 from
      # the deadsnakes PPA. Ubuntu 24.04+ + Debian 12+ have python3.11+
      # in the main repo so the simple path works there.
      if [[ "$DISTRO_ID" == "ubuntu" ]] && [[ "$DISTRO_VERSION" == "22.04" ]]; then
        warn "Ubuntu 22.04 default python3 is 3.10 — adding the deadsnakes PPA for python3.11."
        run "sudo apt-get install -y -qq software-properties-common"
        run "sudo add-apt-repository -y ppa:deadsnakes/ppa"
        run "sudo apt-get update -qq"
        run "sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev"
      else
        # Debian 12+ / Ubuntu 24.04+ — generic name covers it.
        run "sudo apt-get install -y -qq python3 python3-venv python3-dev python3-pip"
        # If the distro python is still < 3.11 (Debian 11 etc.), try the
        # versioned package as a fallback.
        if ! detect_python >/dev/null; then
          warn "Distro python3 is too old; trying explicit python3.11."
          run "sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev || true"
        fi
      fi
      ;;
    dnf|yum)
      # Fedora 39+ and RHEL/Rocky/Alma 9+ ship python3.11 or newer.
      # Strategy: install the generic `python3` first (covers Fedora 40+
      # which is 3.12+), and fall back to the explicit `python3.11`
      # package when that's too old (RHEL 8/9, Rocky 8/9 ship 3.6/3.9 as
      # `python3` but have python3.11 as a separate AppStream package).
      run "sudo $PKG_MGR install -y python3 python3-pip python3-devel"
      if ! detect_python >/dev/null; then
        warn "Distro python3 is too old; installing python3.11 from AppStream."
        run "sudo $PKG_MGR install -y python3.11 python3.11-devel"
      fi
      ;;
    pacman)
      # Arch's `python` package is always recent — no version pinning needed.
      run "sudo pacman -Sy --noconfirm --needed python python-pip"
      ;;
    zypper)
      run "sudo zypper --non-interactive install -y python311 python311-devel python311-pip"
      ;;
  esac

  # Re-detect after install — fail loudly if the package didn't yield a
  # working python3.11+ on PATH (e.g. PPA missing on a non-standard
  # Ubuntu derivative). Skip in --dry-run since no install actually
  # happened; the re-check would always fail and mask the real test
  # signal (which command was emitted).
  if [[ "$DRY_RUN" -eq 0 ]]; then
    PY_INFO="$(detect_python || true)"
    if [[ -z "$PY_INFO" ]]; then
      err "Couldn't find a python3.11+ on PATH after install."
      err "Install one manually for your distro, then re-run."
      exit 1
    fi
    ok "OK installed python $(printf '%s\n' "$PY_INFO" | cut -f2)"
  fi
fi

# ---- 3. pnpm -------------------------------------------------------------
# pnpm install needs curl + ca-certificates already; we installed those in
# the base-packages step above. The shell script writes itself into
# ~/.local/share/pnpm and adds an entry to the user's shell rc — the
# `eval` line below makes it available within THIS script run too.
if command -v pnpm >/dev/null 2>&1; then
  ok "OK pnpm $(pnpm --version)"
else
  case "$PKG_MGR" in
    brew)
      run "brew install pnpm"
      ;;
    pacman)
      run "sudo pacman -Sy --noconfirm --needed pnpm"
      ;;
    *)
      # Universal Linux path: the official install script. Drop into the
      # current shell's PATH so subsequent steps (including dig-install)
      # see pnpm without requiring a logout / re-source.
      run "curl -fsSL https://get.pnpm.io/install.sh | env PNPM_VERSION=latest sh -"
      if [[ "$DRY_RUN" -ne 1 ]]; then
        # pnpm's install script writes its location to ~/.bashrc / ~/.zshrc
        # under SHELL-specific env vars; the canonical path is
        # ~/.local/share/pnpm regardless of shell. Source via env var.
        export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
        case ":$PATH:" in *":$PNPM_HOME:"*) ;; *) export PATH="$PNPM_HOME:$PATH" ;; esac
      fi
      ;;
  esac
  if [[ "$DRY_RUN" -ne 1 ]] && ! command -v pnpm >/dev/null 2>&1; then
    err "pnpm install ran but \`pnpm\` is still not on PATH."
    err "Open a new terminal and re-run this script, OR add \$HOME/.local/share/pnpm to your PATH."
    exit 1
  fi
fi

# ---- 4. JDBC extras: cmake + JDK + ant -----------------------------------
if [[ "$WITH_JDBC" -eq 1 ]]; then
  info "=== --jdbc: cmake + JDK + ant ==="

  if command -v cmake >/dev/null 2>&1; then
    ok "OK cmake $(cmake --version | head -n1 | awk '{print $3}')"
  else
    case "$PKG_MGR" in
      brew)   run "brew install cmake" ;;
      apt)    run "sudo apt-get install -y -qq cmake" ;;
      dnf|yum) run "sudo $PKG_MGR install -y cmake" ;;
      pacman) run "sudo pacman -S --noconfirm cmake" ;;
      zypper) run "sudo zypper --non-interactive install -y cmake" ;;
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
      apt)    run "sudo apt-get install -y -qq default-jdk" ;;
      dnf|yum) run "sudo $PKG_MGR install -y java-17-openjdk-devel" ;;
      pacman) run "sudo pacman -S --noconfirm jdk-openjdk" ;;
      zypper) run "sudo zypper --non-interactive install -y java-17-openjdk-devel" ;;
    esac
  fi

  if command -v ant >/dev/null 2>&1; then
    ok "OK ant $(ant -version 2>/dev/null | awk '{print $4}')"
  else
    case "$PKG_MGR" in
      brew)   run "brew install ant" ;;
      apt)    run "sudo apt-get install -y -qq ant" ;;
      dnf|yum) run "sudo $PKG_MGR install -y ant" ;;
      pacman) run "sudo pacman -S --noconfirm apache-ant" ;;
      zypper) run "sudo zypper --non-interactive install -y ant" ;;
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

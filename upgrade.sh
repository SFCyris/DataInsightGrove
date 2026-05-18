#!/usr/bin/env bash
# upgrade.sh — check GitHub for the latest DataInsightGrove release and
# upgrade the local checkout to it.
#
# Usage:
#   ./upgrade.sh              # check + prompt before upgrading
#   ./upgrade.sh --check      # print whether an update is available, exit
#   ./upgrade.sh --yes        # check + upgrade without prompting
#   ./upgrade.sh --to v0.11.0 # upgrade to a specific tag (skips latest check)
#
# Requires: git, curl, python3 (≥3.11). Optional: gh (preferred when
# present — bypasses the GitHub API rate limit on unauthenticated clients).
set -euo pipefail

REPO="SFCyris/DataInsightGrove"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Pre-flight: required commands must exist before we touch anything.
for cmd in git curl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf '\033[31m%s\033[0m\n' "missing required command: $cmd" >&2
    exit 2
  fi
done

err()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
info() { printf '\033[36m%s\033[0m\n' "$*" >&2; }
ok()   { printf '\033[32m%s\033[0m\n' "$*" >&2; }

CHECK_ONLY=0
YES=0
PIN_TAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)   CHECK_ONLY=1; shift ;;
    --yes|-y)  YES=1; shift ;;
    --to)      PIN_TAG="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    *) err "unknown argument: $1"; exit 2 ;;
  esac
done

# -- current version --------------------------------------------------------
# Source of truth: backend/pyproject.toml. Reading it via Python to keep this
# script free of TOML-parsing tricks. Falls back to git describe if Python
# can't introspect the installed package.

current_version() {
  # Round-4 QA finding: previously this used a regex that took the FIRST
  # line matching ``^version = "..."`` in pyproject.toml. A dependent
  # tool section (e.g. ``[tool.x]\nversion = "9.99"``) would then
  # shadow the real ``[project].version``. Parse properly via tomllib
  # (Python 3.11+, ships in stdlib) so the value is unambiguous.
  python3 - <<'PY'
import pathlib, sys
try:
    import tomllib
except ImportError:  # Python < 3.11 fallback
    import tomli as tomllib  # type: ignore
data = tomllib.loads(pathlib.Path("backend/pyproject.toml").read_text(encoding="utf-8"))
project = data.get("project") or {}
print(project.get("version") or "0.0.0+unknown")
PY
}

CURRENT="$(current_version)"
info "current version: $CURRENT"

# -- latest release ---------------------------------------------------------
# Prefer gh (auth'd, no rate limit). Fall back to curl against the public API.

latest_release() {
  if command -v gh >/dev/null 2>&1; then
    gh api "repos/$REPO/releases/latest" --jq '.tag_name' 2>/dev/null && return 0
  fi
  curl -sSfL --max-time 15 --connect-timeout 5 \
    "https://api.github.com/repos/$REPO/releases/latest" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tag_name",""))'
}

if [[ -n "$PIN_TAG" ]]; then
  TARGET="$PIN_TAG"
  info "pinned target: $TARGET"
else
  if ! TARGET="$(latest_release)" || [[ -z "$TARGET" ]]; then
    err "could not query latest release from github.com/$REPO"
    err "(if behind a corporate proxy, try --to vX.Y.Z to force a tag)"
    exit 3
  fi
  info "latest release: $TARGET"
fi

# Normalise tag → version (strip leading 'v').
TARGET_VERSION="${TARGET#v}"

# Compare via Python so we get proper semver / PEP 440 ordering.
# Pen-tester round-2: previously the heredoc was unquoted (`<<PY`),
# which interpolated $CURRENT and $TARGET_VERSION into Python source
# verbatim — a hostile tag name like `1.0.0"); import os; os.system('…')#`
# escaped the string and ran arbitrary code. Quote the heredoc and pass
# values via env vars so the Python source itself is static.
COMPARE="$(_DIG_CUR="$CURRENT" _DIG_NXT="$TARGET_VERSION" python3 - <<'PY'
import os
from packaging.version import Version
try:
    cur = Version(os.environ["_DIG_CUR"])
    nxt = Version(os.environ["_DIG_NXT"])
except Exception:
    print("invalid")
else:
    if nxt > cur: print("upgrade")
    elif nxt < cur: print("downgrade")
    else: print("equal")
PY
)"

case "$COMPARE" in
  equal)     ok "already on the latest version ($CURRENT)"; exit 0 ;;
  downgrade) err "target $TARGET_VERSION is older than current $CURRENT — aborting (pass --to to force)"; exit 4 ;;
  invalid)   err "could not compare versions ($CURRENT vs $TARGET_VERSION)"; exit 4 ;;
  upgrade)   : ;;
esac

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  ok "upgrade available: $CURRENT → $TARGET_VERSION"
  exit 0
fi

# -- confirm ----------------------------------------------------------------

if [[ "$YES" -ne 1 ]]; then
  printf '\033[33mUpgrade %s → %s? [y/N] \033[0m' "$CURRENT" "$TARGET_VERSION" >&2
  read -r REPLY < /dev/tty
  case "$REPLY" in y|Y|yes|YES) ;; *) info "upgrade declined"; exit 0 ;; esac
fi

# -- pre-flight: refuse on a dirty working tree -----------------------------
if [[ -n "$(git status --porcelain)" ]]; then
  err "working tree has uncommitted changes — commit or stash before upgrading"
  err "(otherwise the upgrade may overwrite your work; this script will NOT force)"
  exit 5
fi

# -- fetch + checkout the target tag ----------------------------------------
info "fetching tags…"
git fetch --tags origin

if ! git rev-parse --verify "$TARGET^{tag}" >/dev/null 2>&1 \
   && ! git rev-parse --verify "$TARGET" >/dev/null 2>&1; then
  err "tag $TARGET not found locally even after fetch — does the release exist?"
  exit 6
fi

info "checking out $TARGET…"
git checkout "$TARGET"

# Round-3 operational finding: `git checkout v1.2.3` lands on a
# DETACHED HEAD. Most users won't notice until they try `git pull` later
# and get "You are not currently on a branch" — by then they're confused
# about whether the upgrade worked. Surface it now with a one-line
# explanation so they know what state the repo is in.
if ! git symbolic-ref -q HEAD >/dev/null 2>&1; then
  info "(repo is now in detached-HEAD state at $TARGET — this is normal for a tag checkout;"
  info " run \`git checkout main\` if you want to move back to the rolling tip later.)"
fi

# -- reinstall the Python package + frontend deps ---------------------------
if [[ -d backend/.venv ]]; then
  info "reinstalling backend in editable mode…"
  ./backend/.venv/bin/pip install -e ./backend
fi

if [[ -f frontend/package.json ]]; then
  info "installing frontend deps…"
  ( cd frontend && (pnpm install || npm install) )
fi

# -- DO NOT write a new marker file here ----------------------------------
#
# Round-2 QA finding: previously this wrote `$TARGET_VERSION` to
# `data/.installed_version`, but the backend's
# `version_state.detect_and_record_version_transition` reads the marker
# on the NEXT BOOT, comparing it to the running `dig.__version__`. After
# the upgrade, both are the new version → `prior == current` → no
# transition event ever fires. The fix wave 1 changed the path but
# preserved the timing bug.
#
# The correct flow is hands-off: the PREVIOUS boot already wrote the
# OLD version into the marker; after `git checkout v$NEW` + reinstall,
# the next boot reads the OLD marker, sees a difference, fires the
# transition event, and rewrites the marker to the new version. Our
# only responsibility is to ensure the marker EXISTS pre-upgrade so
# the comparison has something to compare against.
TARGET_DATA_DIR="${DIG_DATA_DIR:-$REPO_ROOT/data}"
mkdir -p "$TARGET_DATA_DIR"
MARKER="$TARGET_DATA_DIR/.installed_version"
if [[ ! -f "$MARKER" ]]; then
  # First-time run on a fresh checkout — seed the OLD version so the
  # next boot detects the transition cleanly.
  printf '%s\n' "$CURRENT" > "$MARKER"
fi
# Otherwise leave the marker alone — it carries the version of the
# install we're upgrading FROM, and that's exactly what the boot hook
# needs.

ok "upgrade complete: $CURRENT → $TARGET_VERSION"
ok "the backend will run its startup schema-upgrade hook on next boot"

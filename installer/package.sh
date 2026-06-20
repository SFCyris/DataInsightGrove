#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ─────────────────────────────────────────────────────────────────────────────
# installer/package.sh — Build the downloadable DataInsightGrove release archive.
#
# Produces a clean, runnable source bundle of the project — exactly the tracked
# files, none of the working cruft (no .git, node_modules, .venv, data/, build
# output, or internal working folders). A recipient unzips it and runs
# ./install.sh, same as a fresh clone.
#
# Usage:
#   ./installer/package.sh                 # package the current HEAD
#   ./installer/package.sh v1.0.0          # package a specific tag / ref
#   ./installer/package.sh --version 1.2.3 # override the embedded version label
#
# Output (installer/dist/):
#   datainsightgrove-<version>.zip         # versioned, for archival
#   datainsightgrove-latest.zip            # stable name for the "latest" link
#                                          #   (GitHub releases/latest/download/…)
#
# Cross-platform: pure git + zip, runs on macOS and Linux. Build a release by
# tagging first, then packaging that tag:  git tag v1.0.0 && ./installer/package.sh v1.0.0
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_NAME="DataInsightGrove"
ASSET_BASE="datainsightgrove"        # lower-case asset stem (URL-friendly)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"

# ── Colour helpers (mirror the other DIG scripts) ───────────────────────────
if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; X=$'\033[0m'
else
  R=""; G=""; Y=""; C=""; B=""; X=""
fi
section() { printf "\n${B}${C}==> %s${X}\n" "$1"; }
info()    { printf "  ${G}*${X} %s\n" "$1"; }
warn()    { printf "  ${Y}!${X} %s\n" "$1"; }
die()     { printf "\n${R}ERROR:${X} %s\n" "$1" >&2; exit 1; }

# ── Parse args ──────────────────────────────────────────────────────────────
REF="HEAD"
VERSION_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --version) shift; VERSION_OVERRIDE="${1:-}"; [ -n "$VERSION_OVERRIDE" ] || die "--version requires a value"; shift ;;
    --version=*) VERSION_OVERRIDE="${1#*=}"; shift ;;
    -h|--help) sed -n '5,28p' "$0"; exit 0 ;;
    -*) die "Unknown flag: $1" ;;
    *) REF="$1"; shift ;;
  esac
done

cd "$REPO_ROOT"

# ── Preflight ───────────────────────────────────────────────────────────────
section "Preflight"
command -v git >/dev/null 2>&1 || die "git is required."
command -v unzip >/dev/null 2>&1 || die "unzip is required (used to verify the archive)."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Not a git repository: $REPO_ROOT"
git rev-parse --verify --quiet "$REF^{commit}" >/dev/null || die "No such git ref: $REF"
RESOLVED="$(git rev-parse --short "$REF")"
info "Repository : $REPO_ROOT"
info "Packaging  : $REF ($RESOLVED)"

# Version: single source of truth is backend/pyproject.toml, overridable.
if [ -n "$VERSION_OVERRIDE" ]; then
  VERSION="$VERSION_OVERRIDE"
else
  VERSION="$(git show "$REF:backend/pyproject.toml" 2>/dev/null \
            | grep -m1 -E '^version = ' | sed -E 's/^version = "(.*)"/\1/')"
  [ -n "$VERSION" ] || die "Could not read version from backend/pyproject.toml at $REF."
fi
info "Version    : $VERSION"

# Warn (don't block) if packaging HEAD with a dirty tree — the archive reflects
# the committed ref, so uncommitted edits are intentionally excluded.
if [ "$REF" = "HEAD" ] && ! git diff --quiet HEAD 2>/dev/null; then
  warn "Working tree has uncommitted changes — they are NOT in the archive."
  warn "Commit (or tag) first so the package reflects the state you intend to ship."
fi

# ── Build the archive ───────────────────────────────────────────────────────
section "Building archive"
rm -rf "$DIST_DIR"; mkdir -p "$DIST_DIR"

PREFIX="${APP_NAME}-${VERSION}/"
VERSIONED="$DIST_DIR/${ASSET_BASE}-${VERSION}.zip"
LATEST="$DIST_DIR/${ASSET_BASE}-latest.zip"

info "Running git archive (tracked files only — respects .gitignore)…"
git archive --format=zip -9 --prefix="$PREFIX" -o "$VERSIONED" "$REF"
cp "$VERSIONED" "$LATEST"

# ── Verify ──────────────────────────────────────────────────────────────────
section "Verifying"
ENTRIES="$(unzip -l "$VERSIONED" 2>/dev/null | tail -1 | awk '{print $2}')"
[ "${ENTRIES:-0}" -gt 0 ] 2>/dev/null || die "Archive is empty — aborting."
# Sanity: the entry points a user needs must be present.
for must in "${PREFIX}install.sh" "${PREFIX}README.md" "${PREFIX}backend/pyproject.toml"; do
  unzip -l "$VERSIONED" "$must" >/dev/null 2>&1 || die "Archive is missing $must"
done
info "$ENTRIES files in the archive; install.sh, README.md, backend present."

# Hashes + sizes
sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}';
        else sha256sum "$1" | awk '{print $1}'; fi; }
hsize() { du -h "$1" | awk '{print $1}'; }

# ── Done ────────────────────────────────────────────────────────────────────
section "Done"
printf "  ${B}%s${X}  (%s)\n" "$VERSIONED" "$(hsize "$VERSIONED")"
printf "    sha256  %s\n" "$(sha "$VERSIONED")"
printf "  ${B}%s${X}  (%s)\n" "$LATEST" "$(hsize "$LATEST")"
printf "    sha256  %s\n" "$(sha "$LATEST")"
echo ""
info "Next: attach both to a GitHub release. The README's download link resolves"
info "to releases/latest/download/${ASSET_BASE}-latest.zip — keep that asset name."

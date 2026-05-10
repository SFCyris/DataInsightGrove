#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Build DataInsightGrove.app — a tiny SwiftUI/AppKit wrapper that:
#  1. Runs scripts/dig-start.sh on launch
#  2. Opens a WKWebView pointing at the configured web URL
#  3. Runs scripts/dig-stop.sh on quit
#
# Mac-only by design. Linux users use the start/stop shell scripts directly.
# Requires Xcode Command Line Tools (`xcode-select --install`).

set -eu

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAC_DIR="$REPO_ROOT/mac"
BUILD_DIR="$MAC_DIR/build"
APP="$BUILD_DIR/DataInsightGrove.app"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "mac/build.sh: only runs on macOS (uname=$(uname -s))." >&2
  exit 1
fi

if ! command -v swiftc >/dev/null 2>&1; then
  echo "swiftc not found — install Xcode Command Line Tools:" >&2
  echo "  xcode-select --install" >&2
  exit 127
fi

echo "[mac] cleaning $BUILD_DIR"
rm -rf "$BUILD_DIR"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "[mac] compiling DataInsightGrove.swift"
swiftc \
  -O \
  -target arm64-apple-macosx12.0 \
  -framework AppKit \
  -framework WebKit \
  -o "$APP/Contents/MacOS/DataInsightGrove" \
  "$MAC_DIR/DataInsightGrove.swift"

echo "[mac] writing Info.plist (REPO_ROOT=$REPO_ROOT)"
# Use python to do a safe substitution so we don't depend on GNU sed quoting.
python3 - "$MAC_DIR/Info.plist.template" "$APP/Contents/Info.plist" "$REPO_ROOT" <<'PYEOF'
import sys
src, dst, repo = sys.argv[1:]
with open(src) as f:
    body = f.read()
body = body.replace("__DIG_REPO_ROOT__", repo)
with open(dst, "w") as f:
    f.write(body)
PYEOF

# Optional: copy the tree emoji as the app icon if a real .icns isn't bundled.
# (Skipped for now — Finder shows a generic icon. To customize: drop an
# AppIcon.icns into mac/ and uncomment the copy below.)
# cp "$MAC_DIR/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"

echo "[mac] ad-hoc codesigning"
codesign --force --deep --sign - "$APP" 2>/dev/null || true

cat <<EOF

✅ Built: $APP
   open it:  open "$APP"
   or copy:  cp -R "$APP" /Applications/

Notes
- The app reads the same config as the shell scripts (~/.config/dig/config.json).
- On first launch the splash window stays up while dig-start.sh boots (~3-5s).
- Quitting the app runs dig-stop.sh — unless DIG was already running before
  the app launched, in which case the app leaves it alone.
EOF

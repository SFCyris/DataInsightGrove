#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Install the DIG .desktop entry into the user's local applications dir.
#
# After running this, "DataInsightGrove" appears in your GNOME / KDE / XFCE
# application menu and `xdg-open dig://` style launchers can find it.
#
# Uninstall by deleting the .desktop file:
#   rm ~/.local/share/applications/datainsightgrove.desktop
# (and `update-desktop-database ~/.local/share/applications` if you have it).

set -eu

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LINUX_DIR="$REPO_ROOT/linux"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "linux/install.sh: only runs on Linux (uname=$(uname -s))." >&2
  echo "On macOS, use: make mac-app" >&2
  exit 1
fi

DEST_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
DEST="$DEST_DIR/datainsightgrove.desktop"
ICON="$ICON_DIR/datainsightgrove.png"

mkdir -p "$DEST_DIR" "$ICON_DIR"

LAUNCHER="$LINUX_DIR/dig-launch.sh"
chmod +x "$LAUNCHER"

# Try to use a bundled icon if present; otherwise fall back to a standard
# Freedesktop icon name so it still shows something sensible.
if [[ -f "$LINUX_DIR/datainsightgrove.png" ]]; then
  cp "$LINUX_DIR/datainsightgrove.png" "$ICON"
  ICON_NAME="datainsightgrove"
else
  ICON_NAME="utilities-system-monitor"
fi

# Substitute paths into the template (same trick as the Mac build — Python so
# we don't fight GNU vs BSD sed quoting).
python3 - "$LINUX_DIR/datainsightgrove.desktop.template" "$DEST" "$LAUNCHER" "$ICON_NAME" <<'PYEOF'
import sys
src, dst, launcher, icon = sys.argv[1:]
with open(src) as f:
    body = f.read()
body = body.replace("__DIG_LAUNCHER__", launcher)
body = body.replace("__DIG_ICON__", icon)
with open(dst, "w") as f:
    f.write(body)
PYEOF

chmod +x "$DEST"  # gnome-shell sometimes expects this

# Refresh the desktop database if available — silent on failure.
command -v update-desktop-database >/dev/null 2>&1 \
  && update-desktop-database "$DEST_DIR" 2>/dev/null || true

cat <<EOF

✅ Installed: $DEST

Open it from your application launcher (search for "DataInsightGrove"),
or run: gtk-launch datainsightgrove

Uninstall:  rm "$DEST"
EOF

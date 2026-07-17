"""Out-of-tree extension loading — discovery + isolation.

Two discovery channels, both upgrade-immune:

  1. Python entry points (`dig.plugins`, `dig.steps`, `dig.connectors`,
     `dig.routers`) declared in any installed package's `pyproject.toml`.
     Lives in site-packages; never touched by `./upgrade.sh`.

  2. `data/extensions/<name>/` directories on disk. Each holds a
     `manifest.json` describing the extension and arbitrary static files
     served at `/ext/<name>/*`. Lives under `data/`, which is gitignored
     and not touched by upgrades.

Both channels are best-effort: a broken extension logs at WARNING and is
skipped, never blocks DIG startup.
"""
from dig.extensions.loader import (
    DiscoveredExtension,
    DiscoveredFsExtension,
    discover_all,
    discover_entry_points,
    discover_fs_extensions,
    extensions_dir,
)

__all__ = [
    "DiscoveredExtension",
    "DiscoveredFsExtension",
    "discover_all",
    "discover_entry_points",
    "discover_fs_extensions",
    "extensions_dir",
]

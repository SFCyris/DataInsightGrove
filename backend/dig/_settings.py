"""Resolved runtime settings — single source of truth for ports + dirs.

Resolution order (highest priority first):

  1. Process env vars         — DIG_API_HOST, DIG_API_PORT, DIG_WEB_HOST,
                                DIG_WEB_PORT, DIG_DATA_DIR, DIG_LOG_DIR.
                                Also accepts the shorter DIG_HOST / DIG_PORT
                                aliases that uvicorn looks for directly.
  2. Persistent user config   — ~/.config/dig/config.json, written by
                                `scripts/dig_config.py set` (and by
                                `start.sh / install.sh --save`).
  3. Built-in defaults        — DEFAULTS dict below.

The shell scripts use the same precedence via `scripts/dig_config.py
export`, so backend code, the frontend (via NEXT_PUBLIC_DIG_API set in
dig-start.sh), the Mac .app, and the shell utilities all agree on what
host/port they're using. Nothing in the codebase should hardcode a port
fallback independently — if you find one, that's a bug.

If you change the built-in default here, also update the matching default
in `scripts/dig_config.py:DEFAULT` (the two are intentionally duplicated
to keep `scripts/` independent of an installed `backend/.venv`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Built-in defaults — the floor. Mirrored in scripts/dig_config.py:DEFAULT.
DEFAULTS: dict[str, Any] = {
    "api_host": "127.0.0.1",
    "api_port": 8190,
    "web_host": "127.0.0.1",
    "web_port": 3100,
    "data_dir": None,    # None → backend.dig.storage.files picks <repo>/data
    "log_dir": None,     # None → $TMPDIR
}


def _user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "dig" / "config.json"


def _load_persisted() -> dict[str, Any]:
    """Load the persistent user config. Empty dict on any error so the
    backend never refuses to start because of a malformed config file."""
    p = _user_config_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _resolve(env_keys: list[str], cfg_path: list[str], default: Any) -> Any:
    # 1. env
    for k in env_keys:
        v = os.environ.get(k)
        if v is not None and v != "":
            return v
    # 2. persisted config
    cfg = _load_persisted()
    cur: Any = cfg
    for key in cfg_path:
        if not isinstance(cur, dict):
            cur = None
            break
        cur = cur.get(key)
    if cur is not None and cur != "":
        return cur
    # 3. built-in default
    return default


def api_host() -> str:
    return str(_resolve(
        ["DIG_API_HOST", "DIG_HOST"],
        ["api", "host"],
        DEFAULTS["api_host"],
    ))


def api_port() -> int:
    return int(_resolve(
        ["DIG_API_PORT", "DIG_PORT"],
        ["api", "port"],
        DEFAULTS["api_port"],
    ))


def web_host() -> str:
    return str(_resolve(
        ["DIG_WEB_HOST"],
        ["web", "host"],
        DEFAULTS["web_host"],
    ))


def web_port() -> int:
    return int(_resolve(
        ["DIG_WEB_PORT"],
        ["web", "port"],
        DEFAULTS["web_port"],
    ))


def api_url() -> str:
    """Convenience: the canonical API base URL the backend is listening on."""
    return f"http://{api_host()}:{api_port()}"


def web_url() -> str:
    return f"http://{web_host()}:{web_port()}"

#!/usr/bin/env python3
"""Cross-platform config resolver for DIG.

Resolves the effective runtime configuration from (in priority order):

  1. CLI flags (--api-port / --web-port / --data-dir / --config / etc.)
  2. Environment variables (DIG_API_PORT, DIG_WEB_PORT, DIG_DATA_DIR, …)
  3. The JSON config file (path: $DIG_CONFIG, then ~/.config/dig/config.json,
     then <repo>/dig.config.json — first one that exists wins)
  4. Hard-coded defaults

Usage from the shell scripts:

    python3 scripts/dig_config.py show           # pretty-print effective config
    python3 scripts/dig_config.py export         # KEY=VALUE lines suitable for `eval`
    python3 scripts/dig_config.py init           # write a default config file
    python3 scripts/dig_config.py set api.port 9000
    python3 scripts/dig_config.py get api.port
    python3 scripts/dig_config.py path           # print the active config file path

All output is plain ASCII / UTF-8 with no Mac-specific dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "api": {"host": "127.0.0.1", "port": 8080},
    "web": {"host": "127.0.0.1", "port": 3000},
    "dataDir": None,
    "logDir": None,
    "browserPreviewSampleRows": 100_000,
}

ENV_MAP: dict[str, tuple[str, ...]] = {
    "DIG_API_HOST": ("api", "host"),
    "DIG_API_PORT": ("api", "port"),
    "DIG_WEB_HOST": ("web", "host"),
    "DIG_WEB_PORT": ("web", "port"),
    "DIG_DATA_DIR": ("dataDir",),
    "DIG_LOG_DIR": ("logDir",),
}


def _user_config_dir() -> Path:
    """Cross-platform user config dir — same on Linux + macOS for portability.

    We use ~/.config/dig/ on both rather than ~/Library/Application Support/dig
    on macOS, because the user explicitly asked for one consistent layout that
    works on Linux. macOS's Library path is fine but isn't necessary here.
    """
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "dig"


def _candidate_paths() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("DIG_CONFIG")
    if env:
        out.append(Path(env).expanduser())
    out.append(_user_config_dir() / "config.json")
    out.append(REPO_ROOT / "dig.config.json")
    return out


def find_config_path() -> Path | None:
    for p in _candidate_paths():
        if p.is_file():
            return p
    return None


def active_config_path() -> Path:
    """Where would `set` / `init` write?

    Priority: $DIG_CONFIG, then the user dir (default).
    """
    env = os.environ.get("DIG_CONFIG")
    if env:
        return Path(env).expanduser()
    return _user_config_dir() / "config.json"


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _set_path(d: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cur = d
    for k in path[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[path[-1]] = value


def _get_path(d: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def load_config_file() -> dict[str, Any]:
    p = find_config_path()
    if not p:
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"warning: {p} is not valid JSON: {e}", file=sys.stderr)
        return {}


def resolve(
    cli: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose defaults + file + env + CLI flags."""
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    cfg = _deep_merge(cfg, load_config_file())
    for env_key, path in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is None or val == "":
            continue
        coerced: Any = val
        if path[-1] == "port" and val.isdigit():
            coerced = int(val)
        _set_path(cfg, path, coerced)
    if cli:
        cfg = _deep_merge(cfg, cli)
    return cfg


# ---- subcommands ----

def cmd_show(args: argparse.Namespace) -> int:
    cfg = resolve()
    print(json.dumps(cfg, indent=2, sort_keys=True))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Print KEY=VALUE lines suitable for `eval` in a shell."""
    cfg = resolve()
    out: list[str] = [
        f"DIG_API_HOST={shlex.quote(str(cfg['api']['host']))}",
        f"DIG_API_PORT={cfg['api']['port']}",
        f"DIG_WEB_HOST={shlex.quote(str(cfg['web']['host']))}",
        f"DIG_WEB_PORT={cfg['web']['port']}",
    ]
    if cfg.get("dataDir"):
        out.append(f"DIG_DATA_DIR={shlex.quote(cfg['dataDir'])}")
    if cfg.get("logDir"):
        out.append(f"DIG_LOG_DIR={shlex.quote(cfg['logDir'])}")
    print("\n".join(out))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    p = active_config_path()
    if p.exists() and not args.force:
        print(f"already exists: {p}", file=sys.stderr)
        print("re-run with --force to overwrite, or use `set` to change individual values.", file=sys.stderr)
        return 1
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(DEFAULTS, indent=2) + "\n")
    print(f"wrote {p}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    cfg = resolve()
    val = _get_path(cfg, tuple(args.key.split(".")))
    if val is None:
        print("(unset)")
        return 1
    if isinstance(val, (dict, list)):
        print(json.dumps(val, indent=2, sort_keys=True))
    else:
        print(val)
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    p = active_config_path()
    on_disk = json.loads(p.read_text()) if p.exists() else json.loads(json.dumps(DEFAULTS))
    path = tuple(args.key.split("."))
    raw = args.value
    coerced: Any = raw
    if raw.isdigit():
        coerced = int(raw)
    elif raw.lower() in ("true", "false"):
        coerced = raw.lower() == "true"
    elif raw == "null":
        coerced = None
    _set_path(on_disk, path, coerced)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(on_disk, indent=2, sort_keys=True) + "\n")
    print(f"set {args.key} = {coerced!r}  →  {p}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    p = find_config_path()
    if p:
        print(p)
        return 0
    print(active_config_path(), "(not yet created)", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DIG configuration helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="print effective config (defaults + file + env)")
    sub.add_parser("export", help="print KEY=VALUE lines suitable for `eval`")
    init = sub.add_parser("init", help="write a default config file at the active path")
    init.add_argument("--force", action="store_true")
    g = sub.add_parser("get", help="print one config value, e.g. api.port")
    g.add_argument("key")
    s = sub.add_parser("set", help="write one config value, e.g. api.port 9000")
    s.add_argument("key")
    s.add_argument("value")
    sub.add_parser("path", help="print the active config file path")
    args = p.parse_args(argv)
    return {
        "show": cmd_show,
        "export": cmd_export,
        "init": cmd_init,
        "get": cmd_get,
        "set": cmd_set,
        "path": cmd_path,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

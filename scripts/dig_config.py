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
    # ``port`` is HTTP. ``httpsPort`` is the parallel HTTPS listener,
    # served by ``scripts/dig_tls_proxy.py`` which terminates TLS and
    # forwards plain HTTP to ``port``. Both URLs reach the same service.
    # Defaults keep the historical 8090 / 3000 as plain HTTP (no client
    # surprises) and use the canonical ``+ 353`` offset (8443, 3443) for
    # HTTPS — the standard "alt-https" port range.
    "api": {"host": "127.0.0.1", "port": 8090, "httpsPort": 8443},
    "web": {"host": "127.0.0.1", "port": 3000, "httpsPort": 3443},
    "dataDir": None,
    # Default to the canonical Unix system log path. The start script
    # bootstraps the dir with sudo on first run if it doesn't exist /
    # isn't writable, and falls back to a per-user location
    # (~/Library/Logs/DIG on macOS, ~/.local/state/DIG/logs on Linux)
    # if the bootstrap fails or is declined.
    "logDir": "/var/log/DIG",
    "log": {
        # 10 MB × 5 files per stream → 50 MB max for api, 50 MB for web.
        # Rotation is size-based via Python's RotatingFileHandler. The
        # active file is dig-{api,web}.log; rotated files are .1 (newest)
        # through .5 (oldest). Tune via DIG_LOG_MAX_BYTES /
        # DIG_LOG_BACKUP_COUNT, or `dig-config set log.maxBytes 52428800`.
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
    # Self-signed TLS for both API + web. Default on so the auth token
    # is never exposed cleartext on the LAN. ``certFile``/``keyFile``
    # default to None → resolved by scripts/dig_tls.py to
    # ~/.config/dig/tls/dig.{crt,key}. ``autoTrust`` installs the cert
    # into the system trust store on first start (sudo prompt) so
    # browsers don't show "Not Secure." ``additionalSans`` lets you
    # cover extra DNS names / IPs (e.g. a load-balancer hostname).
    "tls": {
        "enabled": True,
        "certFile": None,
        "keyFile": None,
        "autoTrust": True,
        "additionalSans": [],
    },
    "browserPreviewSampleRows": 100_000,
}

ENV_MAP: dict[str, tuple[str, ...]] = {
    "DIG_API_HOST": ("api", "host"),
    "DIG_API_PORT": ("api", "port"),
    "DIG_API_HTTPS_PORT": ("api", "httpsPort"),
    "DIG_WEB_HOST": ("web", "host"),
    "DIG_WEB_PORT": ("web", "port"),
    "DIG_WEB_HTTPS_PORT": ("web", "httpsPort"),
    "DIG_DATA_DIR": ("dataDir",),
    "DIG_LOG_DIR": ("logDir",),
    "DIG_LOG_MAX_BYTES": ("log", "maxBytes"),
    "DIG_LOG_BACKUP_COUNT": ("log", "backupCount"),
    "DIG_TLS_ENABLED": ("tls", "enabled"),
    "DIG_TLS_CERT": ("tls", "certFile"),
    "DIG_TLS_KEY": ("tls", "keyFile"),
    "DIG_TLS_AUTO_TRUST": ("tls", "autoTrust"),
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


def _strip_nulls(obj: Any) -> Any:
    """Drop ``null`` values from a loaded config tree.

    A ``null`` in the on-disk config means "no override — let the default
    win." Without this, an old config file with ``"logDir": null`` would
    silently zap a newly-introduced default. Recurses through nested
    dicts so ``{"log": {"maxBytes": null}}`` falls back too.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if v is None:
                continue
            cleaned = _strip_nulls(v)
            if isinstance(cleaned, dict) and not cleaned:
                # An empty sub-dict after stripping is also "no override".
                continue
            out[k] = cleaned
        return out
    return obj


def load_config_file() -> dict[str, Any]:
    p = find_config_path()
    if not p:
        return {}
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"warning: {p} is not valid JSON: {e}", file=sys.stderr)
        return {}
    return _strip_nulls(raw) if isinstance(raw, dict) else {}


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
        # Numeric coercion: ports + log size/count are ints. Match on the
        # leaf key so we don't accidentally int-coerce string fields.
        if path[-1] in ("port", "httpsPort", "maxBytes", "backupCount") and val.isdigit():
            coerced = int(val)
        elif path[-1] in ("enabled", "autoTrust"):
            coerced = val.lower() in ("1", "true", "yes", "on")
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
        f"DIG_API_HTTPS_PORT={cfg['api'].get('httpsPort', 8443)}",
        f"DIG_WEB_HOST={shlex.quote(str(cfg['web']['host']))}",
        f"DIG_WEB_PORT={cfg['web']['port']}",
        f"DIG_WEB_HTTPS_PORT={cfg['web'].get('httpsPort', 3443)}",
    ]
    if cfg.get("dataDir"):
        out.append(f"DIG_DATA_DIR={shlex.quote(cfg['dataDir'])}")
    if cfg.get("logDir"):
        out.append(f"DIG_LOG_DIR={shlex.quote(cfg['logDir'])}")
    log_cfg = cfg.get("log") or {}
    if log_cfg.get("maxBytes") is not None:
        out.append(f"DIG_LOG_MAX_BYTES={int(log_cfg['maxBytes'])}")
    if log_cfg.get("backupCount") is not None:
        out.append(f"DIG_LOG_BACKUP_COUNT={int(log_cfg['backupCount'])}")
    tls_cfg = cfg.get("tls") or {}
    out.append(f"DIG_TLS_ENABLED={'1' if tls_cfg.get('enabled') else '0'}")
    if tls_cfg.get("certFile"):
        out.append(f"DIG_TLS_CERT={shlex.quote(tls_cfg['certFile'])}")
    if tls_cfg.get("keyFile"):
        out.append(f"DIG_TLS_KEY={shlex.quote(tls_cfg['keyFile'])}")
    out.append(f"DIG_TLS_AUTO_TRUST={'1' if tls_cfg.get('autoTrust') else '0'}")
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

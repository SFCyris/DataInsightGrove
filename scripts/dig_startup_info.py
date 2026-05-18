#!/usr/bin/env python3
"""Emit a DIG startup banner to one or more log files.

Captures everything you'd want pinned to a support ticket without asking
the user a single question:

  - timestamp + hostname
  - DIG version + git SHA
  - OS / kernel / Python / Node versions
  - CPU count, total RAM, disk free in the data dir
  - all DIG_* env vars (sensitive-looking values masked)
  - the resolved effective config (defaults + file + env)

Usage:

    python3 dig_startup_info.py --target /var/log/DIG/dig-api.log [--target ...]

Each --target is appended to (created if missing). Designed to be run by
``dig-start.sh`` immediately before the rotator wrapper takes over the
file — the banner ends up at the top of the freshest log.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Anything matching these regexes in an env var NAME or VALUE position
# gets masked. Conservative on purpose — false positives ("PATH" containing
# a key-shaped substring) are cheaper than leaking a real secret to disk.
_SENSITIVE_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE)", re.IGNORECASE)


def _mask(value: str) -> str:
    """Replace the middle of a secret with stars but keep enough of the
    head + tail that an operator can confirm "yes, that's the right one"
    by eyeballing it."""
    if value is None:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}  ({len(value)} chars)"


def _sh(cmd: list[str], *, cwd: Path | None = None, timeout: float = 5.0) -> str:
    """Run a command, return stdout stripped, never raise. Empty string on failure."""
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _bytes_human(n: int) -> str:
    """1234567 → '1.2 MB'."""
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    f = float(n)
    i = 0
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.1f} {units[i]}"


def _system_info() -> dict[str, str]:
    info: dict[str, str] = {}
    info["host"] = socket.gethostname()
    info["os"] = f"{platform.system()} {platform.release()}"
    info["kernel"] = platform.version()
    info["arch"] = platform.machine()
    info["python"] = sys.version.split()[0]
    node_v = _sh(["node", "--version"]) or "(not found)"
    info["node"] = node_v
    pnpm_v = _sh(["pnpm", "--version"]) or "(not found)"
    info["pnpm"] = pnpm_v

    cpu = os.cpu_count()
    info["cpu_count"] = str(cpu) if cpu else "?"

    # Total RAM — use sysctl on macOS, /proc/meminfo on Linux. Avoid psutil
    # so this script has zero non-stdlib deps (it runs before any venv is
    # guaranteed activated).
    if platform.system() == "Darwin":
        ram_raw = _sh(["sysctl", "-n", "hw.memsize"])
        if ram_raw.isdigit():
            info["ram"] = _bytes_human(int(ram_raw))
    elif platform.system() == "Linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        info["ram"] = _bytes_human(kb * 1024)
                        break
        except OSError:
            pass
    info.setdefault("ram", "?")
    return info


def _disk_free(path: str) -> str:
    try:
        u = shutil.disk_usage(path)
        return f"{_bytes_human(u.free)} free of {_bytes_human(u.total)}"
    except OSError:
        return "?"


def _git_sha() -> str:
    if not (REPO_ROOT / ".git").exists():
        return "(not a git checkout)"
    sha = _sh(["git", "-C", str(REPO_ROOT), "rev-parse", "--short=12", "HEAD"])
    if not sha:
        return "(unknown)"
    dirty = _sh(["git", "-C", str(REPO_ROOT), "status", "--porcelain"])
    return f"{sha}{'-dirty' if dirty else ''}"


def _dig_version() -> str:
    """Pull the version string from package metadata. Falls back to a
    VERSION file or "(unknown)" if neither is available — this script
    runs before the venv is guaranteed importable, so we shell out."""
    # Try the venv's installed package first.
    venv_py = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
    if venv_py.exists():
        v = _sh([
            str(venv_py), "-c",
            "import importlib.metadata as m; print(m.version('dig'))",
        ])
        if v:
            return v
    # Fallbacks: VERSION file, pyproject.toml grep.
    for candidate in ("VERSION", "backend/VERSION"):
        p = REPO_ROOT / candidate
        if p.exists():
            txt = p.read_text().strip()
            if txt:
                return txt
    py_proj = REPO_ROOT / "backend" / "pyproject.toml"
    if py_proj.exists():
        for line in py_proj.read_text().splitlines():
            line = line.strip()
            if line.startswith("version"):
                m = re.search(r'"([^"]+)"', line)
                if m:
                    return m.group(1)
    return "(unknown)"


def _effective_config() -> dict:
    """Return ``dig_config show`` output as a dict. Empty dict if the
    helper isn't importable for any reason — banner still rendered."""
    cfg_py = Path(__file__).with_name("dig_config.py")
    venv_py = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    out = _sh([py, str(cfg_py), "show"])
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


def _dig_env_vars() -> dict[str, str]:
    """All DIG_*-prefixed env vars, alphabetised. Sensitive values masked
    by name (any var matching TOKEN/SECRET/PASSWORD/KEY/PRIVATE)."""
    out: dict[str, str] = {}
    for k, v in sorted(os.environ.items()):
        if not k.startswith("DIG_") and not k.startswith("NEXT_PUBLIC_DIG_"):
            continue
        if _SENSITIVE_NAME.search(k):
            out[k] = _mask(v)
        else:
            out[k] = v
    return out


def _tls_summary() -> dict[str, str]:
    """Best-effort cert summary. Returns {} if no cert / openssl missing."""
    cert = os.environ.get("DIG_TLS_CERT")
    if not cert or not Path(cert).is_file():
        return {}
    try:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("dig_tls.py")), "info"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        info = json.loads(r.stdout) if r.returncode == 0 else {}
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        info = {}
    return info or {}


def render(target_paths: list[str]) -> str:
    """Build the banner string and return it (also useful for tests)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sysinfo = _system_info()
    cfg = _effective_config()
    env_vars = _dig_env_vars()
    tls = _tls_summary()
    data_dir = (cfg.get("dataDir") or os.environ.get("DIG_DATA_DIR")
                or str(REPO_ROOT / "data"))
    log_dir = (cfg.get("logDir") or os.environ.get("DIG_LOG_DIR") or "?")

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"  DIG startup · {now}")
    lines.append("=" * 78)
    lines.append(f"  version    : {_dig_version()}")
    lines.append(f"  git        : {_git_sha()}")
    lines.append(f"  host       : {sysinfo.get('host','?')}")
    lines.append(f"  os         : {sysinfo.get('os','?')}  ({sysinfo.get('arch','?')})")
    lines.append(f"  kernel     : {sysinfo.get('kernel','?')}")
    lines.append(f"  python     : {sysinfo.get('python','?')}")
    lines.append(f"  node       : {sysinfo.get('node','?')}")
    lines.append(f"  pnpm       : {sysinfo.get('pnpm','?')}")
    lines.append(f"  cpu count  : {sysinfo.get('cpu_count','?')}")
    lines.append(f"  ram        : {sysinfo.get('ram','?')}")
    lines.append(f"  data dir   : {data_dir}  ({_disk_free(data_dir)})")
    lines.append(f"  log dir    : {log_dir}")
    if tls:
        lines.append("")
        lines.append("  --- TLS --------------------------------------------------------------------")
        lines.append(f"  cert       : {tls.get('path','?')}")
        lines.append(f"  subject    : {tls.get('subject','?')}")
        lines.append(f"  valid_from : {tls.get('valid_from','?')}")
        lines.append(f"  valid_until: {tls.get('valid_until','?')}")
        lines.append(f"  fingerprint: {tls.get('fingerprint_sha256','?')}")
        sans = tls.get("sans", "")
        if sans:
            lines.append(f"  SANs       : {sans}")
        trusted = tls.get("trusted_in_system_store")
        lines.append(f"  trusted    : {'yes (system trust store)' if trusted else 'no (browser will warn)'}")
    lines.append("")
    lines.append("  --- effective config -------------------------------------------------------")
    if cfg:
        for ln in json.dumps(cfg, indent=2, sort_keys=True).splitlines():
            lines.append(f"  {ln}")
    else:
        lines.append("  (config helper unavailable)")
    lines.append("")
    lines.append("  --- DIG_* env vars ---------------------------------------------------------")
    if env_vars:
        for k, v in env_vars.items():
            lines.append(f"  {k}={v}")
    else:
        lines.append("  (none set)")
    lines.append("")
    lines.append(f"  --- targets: {', '.join(target_paths)}")
    lines.append("=" * 78)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Append a DIG startup banner to one or more log files.")
    p.add_argument(
        "--target", action="append", default=[],
        help="Log file path to append the banner to. May be passed multiple times.",
    )
    p.add_argument(
        "--also-stdout", action="store_true",
        help="Also write the banner to stdout (useful when run interactively).",
    )
    args = p.parse_args()

    if not args.target and not args.also_stdout:
        p.error("pass at least one --target (or --also-stdout for a dry run).")

    banner = render(args.target)

    for path in args.target:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(banner)
        except OSError as e:
            print(f"warning: could not write banner to {path}: {e}", file=sys.stderr)

    if args.also_stdout:
        sys.stdout.write(banner)

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Settings API — server-side preferences, JDBC drivers, global webhooks.

Three resource families:
  - GET/PUT /settings        : key/value preferences (paths, perf, etc.)
  - GET/POST/PUT/DELETE /jdbc-drivers
  - GET/POST/PUT/DELETE /global-webhooks

Settings have a small allow-list of keys; arbitrary keys are rejected so
the API doesn't accumulate junk over time.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.storage.db import get_session
from dig.storage.models import GlobalWebhook, JdbcDriver, Setting

log = logging.getLogger(__name__)


# ---- Schema ---------------------------------------------------------------
#
# Each entry: ( key, default, validator ). The validator is a callable that
# raises ValueError on bad input. Settings outside this allow-list are
# rejected on PUT so the table doesn't accumulate junk.


def _validate_path(v: Any, *, must_exist: bool = False) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError("must be a non-empty string")
    p = Path(v).expanduser()
    if must_exist and not p.exists():
        raise ValueError(f"path does not exist: {v}")
    return str(p)


def _validate_positive_int(v: Any, *, lo: int = 1, hi: int = 1_000_000) -> int:
    try:
        i = int(v)
    except (TypeError, ValueError) as e:
        raise ValueError("must be an integer") from e
    if i < lo or i > hi:
        raise ValueError(f"must be between {lo} and {hi}")
    return i


def _validate_enum(v: Any, allowed: tuple[str, ...]) -> str:
    if v not in allowed:
        raise ValueError(f"must be one of: {', '.join(allowed)}")
    return v


def _validate_string(v: Any, *, max_len: int = 1024, allow_empty: bool = True) -> str:
    if v is None:
        return "" if allow_empty else (_ for _ in ()).throw(ValueError("must not be empty"))
    if not isinstance(v, str):
        raise ValueError("must be a string")
    if not allow_empty and not v.strip():
        raise ValueError("must not be empty")
    if len(v) > max_len:
        raise ValueError(f"must be at most {max_len} characters")
    return v


def _validate_ai_endpoint(v: Any) -> str:
    """``ai_endpoint`` accepts http:// and https:// URLs. Loopback is
    permitted (legitimate for local Ollama / LM Studio installs). Other
    private addresses are rejected unless ``DIG_AI_ALLOW_PRIVATE=1`` —
    same shape as ``DIG_REST_ALLOW_PRIVATE``. Round-3 pen-tester finding
    PEN #8: without this an authenticated user could repoint the AI
    endpoint to an internal HTTP service and have its response (plus
    the AI bearer token) flow back through the AI client.
    """
    s = _validate_string(v, max_len=512, allow_empty=False).strip()
    from urllib.parse import urlsplit
    parts = urlsplit(s)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError(
            f"endpoint must be http:// or https:// — got {parts.scheme!r}"
        )
    if not parts.hostname:
        raise ValueError("endpoint must include a hostname")
    if os.environ.get("DIG_AI_ALLOW_PRIVATE") == "1":
        return s
    # Loopback explicitly OK (Ollama default).
    host = parts.hostname.lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
        return s
    # Otherwise apply the same private-IP guard the REST connector uses.
    try:
        from connectors.rest_api.connector import _is_private_address
        if _is_private_address(parts.hostname):
            raise ValueError(
                f"endpoint host {parts.hostname!r} resolves to a private / "
                "link-local address (other than loopback). Set "
                "DIG_AI_ALLOW_PRIVATE=1 to permit on a trusted host."
            )
    except ImportError:
        pass
    return s


def _validate_float(v: Any, *, lo: float = 0.0, hi: float = 2.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError) as e:
        raise ValueError("must be a number") from e
    if f < lo or f > hi:
        raise ValueError(f"must be between {lo} and {hi}")
    return f


# Allow-list of editable settings. Anything outside this map is rejected.
_SETTINGS_SPEC: dict[str, dict[str, Any]] = {
    "input_dir": {
        "default": None,
        "label": "Input directory",
        "help": "Default folder for uploaded / browsed datasets. Leave blank to use the system default (data/inputs/).",
        "type": "path",
        "validate": lambda v: _validate_path(v, must_exist=True) if v else None,
    },
    "output_dir": {
        "default": None,
        "label": "Output directory",
        "help": "Where pipeline outputs land by default. Leave blank to use data/outputs/<run-id>/.",
        "type": "path",
        "validate": lambda v: _validate_path(v, must_exist=True) if v else None,
    },
    "default_sample_rows": {
        "default": 100_000,
        "label": "Default sample rows",
        "help": "How many rows the live preview loads from each dataset.",
        "type": "integer",
        "validate": lambda v: _validate_positive_int(v, lo=1_000, hi=10_000_000),
    },
    "default_preview_limit": {
        "default": 500,
        "label": "Default preview row limit",
        "help": "Maximum rows shown in the grid below each step. Larger = more context, slower scroll.",
        "type": "integer",
        "validate": lambda v: _validate_positive_int(v, lo=10, hi=10_000),
    },
    "max_concurrent_runs": {
        "default": 4,
        "label": "Max concurrent runs",
        "help": "How many pipelines may execute in parallel before queuing. Match to your CPU core count for throughput.",
        "type": "integer",
        "validate": lambda v: _validate_positive_int(v, lo=1, hi=64),
    },
    "duckdb_threads": {
        "default": 0,
        "label": "DuckDB threads",
        "help": "Threads DuckDB uses for execution. 0 = auto-detect from your CPU.",
        "type": "integer",
        "validate": lambda v: _validate_positive_int(v, lo=0, hi=256),
    },
    "log_level": {
        "default": "INFO",
        "label": "Log level",
        "help": "How chatty the server logs are.",
        "type": "enum",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "validate": lambda v: _validate_enum(v, ("DEBUG", "INFO", "WARNING", "ERROR")),
    },
    "run_history_days": {
        "default": 30,
        "label": "Run history retention (days)",
        "help": "Older run records (and cached intermediates) are pruned after this many days. 0 = keep forever.",
        "type": "integer",
        "validate": lambda v: _validate_positive_int(v, lo=0, hi=3650),
    },
    "auto_detect_index": {
        "default": True,
        "label": "Auto-detect index columns",
        "help": "When profiling a dataset, mark integer columns with all-unique values as 'index' type so duplicates show in red.",
        "type": "boolean",
        "validate": lambda v: bool(v),
    },
    "auto_detect_timezone": {
        "default": True,
        "label": "Auto-detect timezone columns",
        "help": "Mark string columns as 'timezone' when most values look like IANA zones (America/New_York, Europe/Berlin, …).",
        "type": "boolean",
        "validate": lambda v: bool(v),
    },
    # ---- AI assistant settings -------------------------------------------
    # Pluggable LLM provider for the explain / fix-expression / generate-
    # connector features.
    # Keys grouped by ai_* prefix so the frontend can render them as one
    # section. The api_key is masked on read — see _mask_secrets below.
    "ai_enabled": {
        "default": False,
        "label": "Enable AI assistant",
        "help": "Master switch. Off = no AI features in the UI. When on, requires a working endpoint + model below.",
        "type": "boolean",
        "validate": lambda v: bool(v),
    },
    "ai_provider": {
        "default": "local",
        "label": "AI provider",
        "help": "Local = run an Ollama / llama.cpp / vLLM instance on your machine (recommended; privacy + free). OpenAI-compatible = bring your own API key for Anthropic, OpenAI, Groq, OpenRouter, etc.",
        "type": "enum",
        "options": ["local", "openai_compat", "disabled"],
        "validate": lambda v: _validate_enum(v, ("local", "openai_compat", "disabled")),
    },
    "ai_endpoint": {
        "default": "http://localhost:11434/v1",
        "label": "Endpoint URL",
        "help": "OpenAI-compatible /v1 base URL. Defaults to Ollama's loopback. For Anthropic use https://api.anthropic.com/v1; for OpenAI https://api.openai.com/v1.",
        "type": "string",
        "validate": _validate_ai_endpoint,
    },
    "ai_model": {
        "default": "gemma4:e4b",
        "label": "Model",
        "help": "Model identifier the provider expects. For Ollama: `ollama list` shows what you have pulled. Recommended local default: gemma4:e4b (~7 GB, 128K context). For Anthropic try claude-haiku-4-5; for OpenAI gpt-5-mini.",
        "type": "string",
        "validate": lambda v: _validate_string(v, max_len=128, allow_empty=False),
    },
    "ai_api_key": {
        "default": "",
        "label": "API key",
        "help": "Bearer token. Local Ollama doesn't need one; OpenAI / Anthropic / Groq / etc. do. Stored in your local DIG database; never sent anywhere except your configured endpoint.",
        "type": "secret",
        "validate": lambda v: _validate_string(v, max_len=512, allow_empty=True),
    },
    "ai_max_tokens": {
        "default": 4096,
        "label": "Max output tokens",
        "help": "Upper bound on AI response length per call. Higher = more verbose explanations but slower + more costly (for paid providers).",
        "type": "integer",
        "validate": lambda v: _validate_positive_int(v, lo=64, hi=131072),
    },
    "ai_temperature": {
        "default": 0.0,
        "label": "Temperature",
        "help": "Randomness of AI output. 0 = deterministic (best for code generation). 0.7 = creative (best for natural-language explanations).",
        "type": "float",
        "validate": lambda v: _validate_float(v, lo=0.0, hi=2.0),
    },
    "ai_ping_interval_s": {
        "default": 0,
        "label": "Ping interval (seconds)",
        "help": "When > 0, the UI sends a tiny ping to the LLM every N seconds to keep it loaded in memory. Useful for local Ollama / llama.cpp which unload idle models. 0 = off. A safe default is 5 seconds.",
        "type": "integer",
        "validate": lambda v: _validate_positive_int(v, lo=0, hi=600),
    },

    # ---- Boot-time config (persists in ~/.config/dig/config.json) ----
    # These are read by scripts/dig-start.sh + dig_log_rotate.py +
    # dig_tls_proxy.py BEFORE the FastAPI app comes up. We surface them
    # in the same Settings UI for discoverability, but writes round-trip
    # through scripts/dig_config.py so the file stays authoritative.
    # ``requires_restart`` flags them so the UI can show "(takes effect
    # on next restart)". ``group="boot"`` lets the UI cluster them in
    # their own section.

    "logDir": {
        "default": "/var/log/DIG",
        "label": "Log directory",
        "help": "Where dig-start.sh writes the rotated log streams. Default /var/log/DIG (Unix-canonical; bootstrapped with sudo on first run, falls back to ~/Library/Logs/DIG on macOS or ~/.local/state/DIG/logs on Linux if sudo declined). Takes effect on next restart.",
        "type": "string",
        "source": "config_file",
        "group": "boot",
        "requires_restart": True,
        "validate": lambda v: _validate_string(v, max_len=1024, allow_empty=False),
    },
    "log.maxBytes": {
        "default": 10 * 1024 * 1024,
        "label": "Log file size limit (bytes)",
        "help": "Per-stream rotation threshold. When the active log file reaches this size, it's rolled (.log → .log.1) and a fresh file is started. Default 10 MB. Takes effect on next restart.",
        "type": "integer",
        "source": "config_file",
        "group": "boot",
        "requires_restart": True,
        "validate": lambda v: _validate_positive_int(v, lo=1024, hi=10 * 1024 * 1024 * 1024),
    },
    "log.backupCount": {
        "default": 5,
        "label": "Log rotations kept",
        "help": "How many rotated log files to keep per stream (.log.1 .. .log.N). Older files are pruned. Default 5 → 50 MB max history per stream. Takes effect on next restart.",
        "type": "integer",
        "source": "config_file",
        "group": "boot",
        "requires_restart": True,
        "validate": lambda v: _validate_positive_int(v, lo=0, hi=1000),
    },

    "tls.enabled": {
        "default": True,
        "label": "HTTPS enabled",
        "help": "When on, scripts/dig_tls_proxy.py terminates HTTPS on api.httpsPort + web.httpsPort and forwards plain HTTP to the primary ports. Off = HTTP-only (plain http:// URLs are always live regardless). Takes effect on next restart.",
        "type": "boolean",
        "source": "config_file",
        "group": "boot",
        "requires_restart": True,
        "validate": lambda v: bool(v),
    },
    "tls.autoTrust": {
        "default": True,
        "label": "Auto-install cert in system trust store",
        "help": "On first start, prompt for sudo to install the self-signed cert into the system keychain so browsers stop showing 'Not Secure'. The attempt happens exactly once — once attempted (successful or declined) subsequent restarts skip it. Re-trigger with `./scripts/dig_tls.py trust`. Takes effect on next restart.",
        "type": "boolean",
        "source": "config_file",
        "group": "boot",
        "requires_restart": True,
        "validate": lambda v: bool(v),
    },

    "api.httpsPort": {
        "default": 8443,
        "label": "API HTTPS port",
        "help": "Port the TLS proxy listens on for the API. The plain HTTP port (default 8090) stays in 'api.port'. Takes effect on next restart.",
        "type": "integer",
        "source": "config_file",
        "group": "boot",
        "requires_restart": True,
        "validate": lambda v: _validate_positive_int(v, lo=1, hi=65535),
    },
    "web.httpsPort": {
        "default": 3443,
        "label": "Web HTTPS port",
        "help": "Port the TLS proxy listens on for the web UI. The plain HTTP port (default 3000) stays in 'web.port'. Takes effect on next restart.",
        "type": "integer",
        "source": "config_file",
        "group": "boot",
        "requires_restart": True,
        "validate": lambda v: _validate_positive_int(v, lo=1, hi=65535),
    },
}


# ---- Boot-time config-file passthrough ------------------------------------
#
# Some settings have to be honoured BEFORE the FastAPI app starts (log
# paths, log rotation, TLS cert paths, the HTTPS port the TLS proxy
# binds to). Those can't live in the SQLite ``settings`` table, because
# scripts/dig-start.sh needs them before the DB is touched. They live
# in ~/.config/dig/config.json instead — single source of truth across
# every dig-* shell script and the FastAPI process.
#
# We expose them in the same Settings UI as everything else, but route
# their GET / PUT through scripts/dig_config.py so writes land in the
# right file. ``group="boot"`` + ``requires_restart=True`` flag them in
# the response so the UI can render the right hint next to each field.

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DIG_CONFIG_HELPER = _REPO_ROOT / "scripts" / "dig_config.py"


def _config_file_get(dotted_path: str) -> Any:
    """Read a single dotted-key from the resolved config.

    Returns None if anything fails — UI then falls back to the spec's
    default. ``dotted_path`` looks like ``log.maxBytes`` or
    ``tls.enabled`` (the same shape the helper's ``get`` subcommand
    accepts)."""
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, str(_DIG_CONFIG_HELPER), "get", dotted_path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode != 0:
            return None
        raw = r.stdout.strip()
        # The helper prints "(unset)" when the key isn't in the merged
        # config. Treat it as None so the UI shows the spec default.
        if not raw or raw == "(unset)":
            return None
        # Try to coerce booleans + ints; the helper prints the Python repr
        # for these, which is JSON-compatible for our types.
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        if raw.lstrip("-").isdigit():
            return int(raw)
        return raw
    except (OSError, subprocess.SubprocessError):
        return None


def _config_file_set(dotted_path: str, value: Any) -> None:
    """Persist a value to the config file via the helper's ``set``
    subcommand. Raises ValueError on failure so the PUT endpoint can
    surface a 400."""
    import subprocess
    # The helper accepts strings; it coerces "true"/"false"/digits/null
    # itself, so we just stringify uniformly.
    str_val = "null" if value is None else (
        "true"  if value is True  else
        "false" if value is False else
        str(value)
    )
    r = subprocess.run(
        [sys.executable, str(_DIG_CONFIG_HELPER), "set", dotted_path, str_val],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if r.returncode != 0:
        raise ValueError(r.stderr.strip() or r.stdout.strip() or "config write failed")


# Settings whose ``"source": "config_file"`` lives in _SETTINGS_SPEC
# instead of the DB. Maps the public key → dotted path in config.json.
# Lookup table extracted so list_settings + set_setting both reference
# the same map; no risk of one path serialising while the other reads
# from the DB.
_CONFIG_FILE_PATHS: dict[str, str] = {
    "log.maxBytes":          "log.maxBytes",
    "log.backupCount":       "log.backupCount",
    "logDir":                "logDir",
    "tls.enabled":           "tls.enabled",
    "tls.autoTrust":         "tls.autoTrust",
    "api.httpsPort":         "api.httpsPort",
    "web.httpsPort":         "web.httpsPort",
}


# Setting keys whose values must never be returned to the frontend in
# clear text — masked to the first/last few characters in the GET path.
_SECRET_KEYS = frozenset({"ai_api_key"})


def _mask_secret(value: Any) -> str:
    """Mask an API-key-shaped string. Returns "" for empty input,
    otherwise something like 'sk-…abcd' that confirms a value is set
    without revealing it."""
    if not value:
        return ""
    s = str(value)
    if len(s) <= 6:
        return "•" * len(s)
    return f"{s[:3]}…{s[-4:]}"


router = APIRouter(prefix="/settings", tags=["settings"])


# ---- Filesystem browser ---------------------------------------------------
#
# Endpoint backing the directory-picker modal in the settings UI. Browsers
# can't expose a real OS path picker for security reasons, so we ship our
# own server-side browser: the modal calls /fs/browse?path=… to list the
# subdirectories of a given path, and the user navigates one level at a
# time. Always returns the absolute, fully-resolved path so the value the
# user picks matches what the backend will actually use.

fs_router = APIRouter(prefix="/fs", tags=["settings"])


class FsEntry(BaseModel):
    name: str
    is_dir: bool


class FsBrowseOut(BaseModel):
    path: str
    parent: str | None
    home: str
    entries: list[FsEntry]
    exists: bool


def _resolve_browse_path(raw: str | None) -> Path:
    """Resolve and normalize a browse path. Defaults to $HOME when empty."""
    if not raw or not raw.strip():
        return Path.home()
    expanded = Path(raw).expanduser()
    # `.resolve()` collapses ../, follows symlinks, and gives us a stable
    # absolute path. strict=False so we can show "doesn't exist" gracefully
    # rather than 404'ing the whole call.
    return expanded.resolve(strict=False)


@fs_router.get("/browse", response_model=FsBrowseOut)
async def fs_browse(path: str | None = None) -> FsBrowseOut:
    """List the subdirectories of `path` (defaults to the user's home).

    Returns:
      - path: the resolved absolute path being shown
      - parent: the parent directory's absolute path, or None at the root
      - home: $HOME — the picker uses this for a "🏠 Home" shortcut
      - entries: subdirectories, alphabetical, hidden ones (starting with ".")
                 dropped because they bloat the list and are rarely intended
                 destinations for input/output data
      - exists: whether `path` actually exists on disk

    No path is rejected outright — the picker shows "(doesn't exist)" if
    the user types or arrives at a missing directory. This keeps the UX
    forgiving (you can paste a half-typed path and fix it visually) without
    leaking arbitrary filesystem error messages.
    """
    p = _resolve_browse_path(path)
    home = str(Path.home())

    if not p.exists():
        return FsBrowseOut(path=str(p), parent=str(p.parent), home=home, entries=[], exists=False)
    if not p.is_dir():
        # User pointed at a file — show its parent's contents instead, but
        # report the actual resolved path so they can see where they ended up.
        p = p.parent

    try:
        children = sorted(p.iterdir(), key=lambda x: x.name.lower())
    except PermissionError:
        # Read-blocked → empty list with parent set so the user can navigate
        # back out. We don't 403 because the surrounding directory may still
        # be enumerable.
        return FsBrowseOut(
            path=str(p), parent=str(p.parent) if p.parent != p else None,
            home=home, entries=[], exists=True,
        )

    entries: list[FsEntry] = []
    for child in children:
        # Skip hidden + permission-denied entries silently.
        if child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if is_dir:
            entries.append(FsEntry(name=child.name, is_dir=True))

    return FsBrowseOut(
        path=str(p),
        parent=str(p.parent) if p.parent != p else None,
        home=home,
        entries=entries,
        exists=True,
    )


class SettingValue(BaseModel):
    value: Any | None = None


class SettingDescriptor(BaseModel):
    key: str
    value: Any | None = None
    default: Any | None = None
    label: str
    help: str
    type: str
    options: list[str] | None = None
    # Boot-time settings persist in ~/.config/dig/config.json instead of
    # the SQLite ``settings`` table — they're read by scripts/dig-start.sh
    # before uvicorn comes up. The UI surfaces these alongside the normal
    # settings but tags them so it can show "(requires restart)" next to
    # the field. Optional fields default to false / null on the wire.
    requires_restart: bool = False
    group: str = "general"


def _present_value(key: str, value: Any) -> Any:
    """Mask secret-typed settings so the frontend never holds the
    plaintext. The user can still SET the value (write-only), they
    just can't read it back."""
    if key in _SECRET_KEYS:
        return _mask_secret(value)
    return value


@router.get("", response_model=list[SettingDescriptor])
async def list_settings(session: AsyncSession = Depends(get_session)) -> list[SettingDescriptor]:
    rows = (await session.execute(select(Setting))).scalars().all()
    saved = {r.key: r.value for r in rows}
    out: list[SettingDescriptor] = []
    for key, spec in _SETTINGS_SPEC.items():
        # Boot-time settings live in ~/.config/dig/config.json instead of
        # the SQLite settings table — read them through dig_config.py so
        # the UI sees the same value the start script would see at boot.
        if spec.get("source") == "config_file":
            dotted = _CONFIG_FILE_PATHS.get(key, key)
            raw = _config_file_get(dotted)
            if raw is None:
                raw = spec["default"]
        else:
            raw = saved.get(key, spec["default"])
        out.append(SettingDescriptor(
            key=key,
            value=_present_value(key, raw),
            default=_present_value(key, spec["default"]),
            label=spec["label"],
            help=spec["help"],
            type=spec["type"],
            options=spec.get("options"),
            requires_restart=bool(spec.get("requires_restart", False)),
            group=spec.get("group", "general"),
        ))
    return out


@router.put("/{key}", response_model=SettingDescriptor)
async def set_setting(
    key: str,
    body: SettingValue,
    session: AsyncSession = Depends(get_session),
) -> SettingDescriptor:
    spec = _SETTINGS_SPEC.get(key)
    if spec is None:
        raise HTTPException(404, f"unknown setting key '{key}'")

    # Boot-time settings round-trip through dig_config.py so the
    # ~/.config/dig/config.json file remains the single source of
    # truth — the SQLite settings table never sees them.
    if spec.get("source") == "config_file":
        try:
            validated = spec["validate"](body.value)
        except ValueError as e:
            raise HTTPException(400, f"{key}: {e}") from e
        try:
            _config_file_set(_CONFIG_FILE_PATHS.get(key, key), validated)
        except ValueError as e:
            raise HTTPException(500, f"could not persist '{key}' to config file: {e}") from e
        return SettingDescriptor(
            key=key,
            value=_present_value(key, validated),
            default=_present_value(key, spec["default"]),
            label=spec["label"], help=spec["help"], type=spec["type"],
            options=spec.get("options"),
            requires_restart=True,
            group=spec.get("group", "boot"),
        )

    # Round-3 pen-tester: the GET path masks secret values to
    # ``sk-…abcd`` so the cleartext never leaves the server. The
    # frontend redisplays the masked form in the input. If the user
    # clicks Save without retyping, the PUT round-trip writes that
    # placeholder back as the new "secret" — silently clobbering the
    # real key with three chars + an ellipsis. Detect the mask sentinel
    # (``…`` / U+2026, which never appears in legitimate API keys) and
    # treat the submission as a no-op: the existing stored value stays.
    existing = await session.get(Setting, key)
    if (
        key in _SECRET_KEYS
        and isinstance(body.value, str)
        and "…" in body.value
    ):
        if existing is None:
            raise HTTPException(
                400,
                f"{key}: received masked placeholder but no existing secret is stored; "
                "please paste the real API key",
            )
        validated = existing.value
    else:
        try:
            validated = spec["validate"](body.value)
        except ValueError as e:
            raise HTTPException(400, f"{key}: {e}") from e
        if existing is None:
            session.add(Setting(key=key, value=validated))
        else:
            existing.value = validated
        await session.commit()
    return SettingDescriptor(
        key=key,
        value=_present_value(key, validated),
        default=_present_value(key, spec["default"]),
        label=spec["label"], help=spec["help"], type=spec["type"],
        options=spec.get("options"),
        requires_restart=bool(spec.get("requires_restart", False)),
        group=spec.get("group", "general"),
    )


# ---- JDBC drivers ---------------------------------------------------------

drivers_router = APIRouter(prefix="/jdbc-drivers", tags=["settings"])


class JdbcDriverIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    driverClass: str = Field(min_length=1, max_length=255)
    jarPath: str = Field(min_length=1)
    urlTemplate: str | None = None
    notes: str | None = None


class JdbcDriverOut(JdbcDriverIn):
    id: str


def _driver_to_out(d: JdbcDriver) -> JdbcDriverOut:
    return JdbcDriverOut(
        id=d.id, name=d.name, driverClass=d.driver_class, jarPath=d.jar_path,
        urlTemplate=d.url_template, notes=d.notes,
    )


@drivers_router.get("", response_model=list[JdbcDriverOut])
async def list_drivers(session: AsyncSession = Depends(get_session)) -> list[JdbcDriverOut]:
    rows = (await session.execute(select(JdbcDriver).order_by(JdbcDriver.name))).scalars().all()
    return [_driver_to_out(d) for d in rows]


@drivers_router.post("", response_model=JdbcDriverOut, status_code=201)
async def create_driver(
    body: JdbcDriverIn,
    session: AsyncSession = Depends(get_session),
) -> JdbcDriverOut:
    # Verify the JAR path exists at registration time — bad paths surface
    # here, not later inside an opaque jaydebeapi error.
    if not Path(body.jarPath).expanduser().exists():
        raise HTTPException(400, f"jarPath does not exist: {body.jarPath}")
    d = JdbcDriver(
        id=str(ULID()), name=body.name, driver_class=body.driverClass,
        jar_path=body.jarPath, url_template=body.urlTemplate, notes=body.notes,
    )
    session.add(d)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(409, f"a driver named '{body.name}' already exists") from e
    return _driver_to_out(d)


@drivers_router.put("/{driver_id}", response_model=JdbcDriverOut)
async def update_driver(
    driver_id: str,
    body: JdbcDriverIn,
    session: AsyncSession = Depends(get_session),
) -> JdbcDriverOut:
    d = await session.get(JdbcDriver, driver_id)
    if d is None:
        raise HTTPException(404, "driver not found")
    if not Path(body.jarPath).expanduser().exists():
        raise HTTPException(400, f"jarPath does not exist: {body.jarPath}")
    d.name = body.name
    d.driver_class = body.driverClass
    d.jar_path = body.jarPath
    d.url_template = body.urlTemplate
    d.notes = body.notes
    await session.commit()
    return _driver_to_out(d)


@drivers_router.delete("/{driver_id}", status_code=204)
async def delete_driver(
    driver_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    d = await session.get(JdbcDriver, driver_id)
    if d is None:
        raise HTTPException(404, "driver not found")
    await session.delete(d)
    await session.commit()


# ── JDBC test connection ─────────────────────────────────────────────────
# Exercises the same _connect() the connector uses, on the form values the
# user has typed. Returns the result in the body (ok=true/false) so the UI
# never sees an HTTP error for a bad cred / unreachable host — those are
# legitimate "test results", not API failures.


class JdbcTestIn(BaseModel):
    """Ad-hoc test parameters. Not persisted — the URL + credentials are
    only used to open and close one connection. The driverClass and jarPath
    are the same as the saved driver record."""
    driverClass: str = Field(min_length=1, max_length=255)
    jarPath: str = Field(min_length=1)
    url: str | None = Field(
        default=None,
        description=(
            "Optional JDBC URL. With a URL, we try a real connection. Without, "
            "we only verify the JAR exists and the driver class can be loaded."
        ),
    )
    username: str | None = None
    password: str | None = None


class JdbcTestOut(BaseModel):
    ok: bool
    # Human-readable summary the UI shows next to the green check / red X.
    # Examples:
    #   "Connected · PostgreSQL 16.2"
    #   "Driver class loaded (no URL given for full test)"
    #   "Authentication failed: password authentication failed for user 'demo'"
    message: str
    latencyMs: int | None = None
    # Set when the JDBC driver reports its product name + version. Useful as
    # a sanity check that the user pointed at the database they intended.
    serverInfo: str | None = None


@drivers_router.post("/test", response_model=JdbcTestOut)
async def test_driver_connection(body: JdbcTestIn) -> JdbcTestOut:
    """Attempt a quick connect using the supplied JDBC params.

    Always returns 200 — the body's ``ok`` flag tells the UI whether the
    test succeeded. Failures land in ``message`` so the user sees the
    underlying JDBC driver error verbatim (which is invariably the most
    useful thing for diagnosing a bad URL / firewall / wrong creds).
    """
    import asyncio as _asyncio
    import time as _time

    from connectors.jdbc.connector import _connect, _resolve_jars  # type: ignore[import-not-found]

    # Cheap pre-flight: stat the jar before paying for the JVM. Bad paths
    # are by far the most common cause of a failed test — surfacing them
    # without firing up the JVM keeps "fix typo, retry" cheap.
    try:
        _resolve_jars(body.jarPath)
    except (FileNotFoundError, ValueError) as e:
        return JdbcTestOut(ok=False, message=str(e))

    if not body.url:
        # No URL → we can't actually connect. Verifying the driver class
        # *registers* loosely (jaydebeapi finds it via the jar manifest),
        # but the user really wants the full handshake — tell them so.
        return JdbcTestOut(
            ok=False,
            message=(
                "Provide a JDBC URL to run a real connection test "
                "(jar + driver class look reachable)."
            ),
        )

    options = {
        "driverClass": body.driverClass,
        "jarPath": body.jarPath,
        "username": body.username,
        "password": body.password,
    }

    def _try_connect() -> tuple[bool, str, str | None]:
        # Returns (ok, message, server_info_or_none).
        t0 = _time.perf_counter()
        try:
            conn = _connect(body.url or "", options)
        except FileNotFoundError as e:
            return False, str(e), None
        except ValueError as e:
            # Our own validation (bad URL prefix, missing required fields).
            return False, str(e), None
        except Exception as e:  # noqa: BLE001
            # jaydebeapi wraps the JDBC SQLException — the str() form is
            # already the most actionable thing we can show. Strip the
            # noisy java stack trace prefix when present.
            msg = str(e)
            if "java.sql." in msg:
                msg = msg.split("java.sql.")[-1]
            return False, msg, None
        try:
            # Pull product name + version via JDBC's DatabaseMetaData when
            # available; this is the canonical sanity check ("yes, you
            # really did reach the right database"). Best-effort: drivers
            # that don't expose it just fall back to "Connected".
            server: str | None = None
            try:
                meta = conn.jconn.getMetaData()
                product = meta.getDatabaseProductName()
                version = meta.getDatabaseProductVersion()
                if product:
                    server = f"{product} {version}".strip()
            except Exception:  # noqa: BLE001
                server = None
            elapsed = int((_time.perf_counter() - t0) * 1000)
            msg = f"Connected · {elapsed}ms"
            return True, msg, server
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # Bound the test — a hung TCP connect can wait a *long* time. 15 s is
    # generous for legit slow VPNs and short for hostile networks.
    try:
        ok, message, server = await _asyncio.wait_for(
            _asyncio.to_thread(_try_connect), timeout=15.0,
        )
    except _asyncio.TimeoutError:
        return JdbcTestOut(
            ok=False,
            message=(
                "Connection test timed out after 15s. Check the URL, "
                "the host's reachability, and any firewalls / VPN."
            ),
        )

    latency_ms: int | None = None
    if ok and " · " in message and message.endswith("ms"):
        try:
            latency_ms = int(message.split(" · ")[-1].rstrip("ms"))
        except ValueError:
            latency_ms = None
    return JdbcTestOut(ok=ok, message=message, latencyMs=latency_ms, serverInfo=server)


# ---- Global webhooks ------------------------------------------------------

webhooks_router = APIRouter(prefix="/global-webhooks", tags=["settings"])


class GlobalWebhookIn(BaseModel):
    label: str | None = None
    url: str = Field(min_length=1)
    on: str = "always"  # always | succeeded | failed
    secret: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool = True


class GlobalWebhookOut(GlobalWebhookIn):
    id: str


_HEADER_SECRET_KEYS = {"authorization", "x-api-key", "x-auth-token", "cookie"}


def _mask_webhook_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    if not headers:
        return headers
    return {
        k: (_mask_secret(v) if k.lower() in _HEADER_SECRET_KEYS else v)
        for k, v in headers.items()
    }


def _webhook_to_out(w: GlobalWebhook) -> GlobalWebhookOut:
    # Mask the HMAC signing secret and any auth-shaped headers on read.
    # The settings endpoints use the same masking pattern for the AI api_key
    # (see _mask_secret above); webhooks were missed in the original wiring.
    return GlobalWebhookOut(
        id=w.id, label=w.label, url=w.url, on=w.on,
        secret=_mask_secret(w.secret) if w.secret else None,
        headers=_mask_webhook_headers(w.headers),
        enabled=w.enabled,
    )


def _validate_webhook_in(body: GlobalWebhookIn) -> None:
    if body.on not in ("always", "succeeded", "failed", "triggered"):
        raise HTTPException(400, "on must be 'always', 'succeeded', 'failed', or 'triggered'")
    if not (body.url.startswith("http://") or body.url.startswith("https://")):
        raise HTTPException(400, "url must start with http:// or https://")


@webhooks_router.get("", response_model=list[GlobalWebhookOut])
async def list_webhooks(session: AsyncSession = Depends(get_session)) -> list[GlobalWebhookOut]:
    rows = (await session.execute(select(GlobalWebhook).order_by(GlobalWebhook.created_at))).scalars().all()
    return [_webhook_to_out(w) for w in rows]


@webhooks_router.post("", response_model=GlobalWebhookOut, status_code=201)
async def create_webhook(
    body: GlobalWebhookIn,
    session: AsyncSession = Depends(get_session),
) -> GlobalWebhookOut:
    _validate_webhook_in(body)
    w = GlobalWebhook(
        id=str(ULID()), label=body.label, url=body.url, on=body.on,
        secret=body.secret, headers=body.headers, enabled=body.enabled,
    )
    session.add(w)
    await session.commit()
    return _webhook_to_out(w)


@webhooks_router.put("/{webhook_id}", response_model=GlobalWebhookOut)
async def update_webhook(
    webhook_id: str,
    body: GlobalWebhookIn,
    session: AsyncSession = Depends(get_session),
) -> GlobalWebhookOut:
    w = await session.get(GlobalWebhook, webhook_id)
    if w is None:
        raise HTTPException(404, "webhook not found")
    _validate_webhook_in(body)
    w.label = body.label
    w.url = body.url
    w.on = body.on
    # If the inbound `secret` looks like the masked form returned by GET
    # (contains the masking ellipsis), keep the existing secret rather than
    # overwriting it. Same for auth-shaped headers. Lets the UI round-trip
    # the row without round-tripping the secret in plaintext.
    if body.secret is None or "…" not in (body.secret or ""):
        w.secret = body.secret
    if body.headers is not None:
        merged: dict[str, str] = dict(body.headers)
        existing = w.headers or {}
        for k, v in merged.items():
            if k.lower() in _HEADER_SECRET_KEYS and v and "…" in v:
                merged[k] = existing.get(k, v)
        w.headers = merged
    else:
        w.headers = body.headers
    w.enabled = body.enabled
    await session.commit()
    return _webhook_to_out(w)


@webhooks_router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    w = await session.get(GlobalWebhook, webhook_id)
    if w is None:
        raise HTTPException(404, "webhook not found")
    await session.delete(w)
    await session.commit()


# ---- Helper for jobs/manager.py: load all enabled global webhooks ----------


async def load_enabled_global_webhooks() -> list[dict[str, Any]]:
    """Returns enabled global webhooks shaped like the per-pipeline Webhook
    pydantic model so jobs/webhooks.dispatch can treat them identically."""
    from dig.storage.db import SessionLocal
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(GlobalWebhook).where(GlobalWebhook.enabled == True)  # noqa: E712
        )).scalars().all()
    return [{
        "url": w.url, "on": w.on, "secret": w.secret,
        "headers": w.headers or {}, "label": w.label,
    } for w in rows]

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
        "validate": lambda v: _validate_string(v, max_len=512, allow_empty=False),
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
        raw = saved.get(key, spec["default"])
        out.append(SettingDescriptor(
            key=key,
            value=_present_value(key, raw),
            default=_present_value(key, spec["default"]),
            label=spec["label"],
            help=spec["help"],
            type=spec["type"],
            options=spec.get("options"),
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
    try:
        validated = spec["validate"](body.value)
    except ValueError as e:
        raise HTTPException(400, f"{key}: {e}") from e

    existing = await session.get(Setting, key)
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

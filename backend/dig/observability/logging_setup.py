"""Optional JSON log formatter behind `DIG_LOG_FORMAT=json`.

Default behavior (unset / `text`): keep the friendly Python `logging`
output developers expect.

When `DIG_LOG_FORMAT=json`: every record becomes a one-line JSON object
with `time`, `level`, `logger`, `message`, optional `error_code`,
optional `extra` (everything passed via `logger.info(..., extra={...})`),
and the traceback formatted as a single-line array of frame strings.

Drop-in callable from anywhere — `configure_logging()` is idempotent and
safe to call repeatedly; subsequent calls swap the handler without
piling up duplicate handlers on the root logger.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


_RESERVED = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Picks up `error_code=` from extras automatically — operators grep for
    `DIG_E_` to find known failure modes.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003 (Python stdlib name)
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info).splitlines()
        # Forward every user-supplied `extra={...}` field, minus the
        # standard LogRecord attributes that aren't useful to consumers.
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in _RESERVED and not k.startswith("_")
        }
        if extras:
            error_code = extras.pop("error_code", None)
            if error_code is not None:
                payload["error_code"] = error_code
            if extras:
                payload["extra"] = extras
        return json.dumps(payload, default=str, separators=(",", ":"))


def is_json_logging() -> bool:
    """True when DIG_LOG_FORMAT=json. Public so callers can adapt their output."""
    return os.environ.get("DIG_LOG_FORMAT", "").strip().lower() == "json"


def configure_logging(*, level: int | None = None) -> None:
    """Install the configured handler on the root logger. Idempotent.

    Honors:
      - DIG_LOG_FORMAT=json  → JSON-line output to stderr
      - DIG_LOG_LEVEL=DEBUG  → root level override (default INFO)

    Safe to call multiple times — every call replaces the existing
    handler set rather than appending.
    """
    root = logging.getLogger()
    # Remove any handlers we previously installed; preserve anything else
    # (e.g. pytest's caplog) by tagging our own handlers with a marker.
    for h in list(root.handlers):
        if getattr(h, "_dig_managed", False):
            root.removeHandler(h)

    env_level = os.environ.get("DIG_LOG_LEVEL", "").strip().upper()
    resolved_level: int
    if level is not None:
        resolved_level = level
    elif env_level:
        resolved_level = getattr(logging, env_level, logging.INFO)
    else:
        resolved_level = logging.INFO

    handler: logging.Handler = logging.StreamHandler(stream=sys.stderr)
    handler._dig_managed = True  # type: ignore[attr-defined]
    if is_json_logging():
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(resolved_level)

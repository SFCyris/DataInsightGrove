"""Stable error-code vocabulary for DIG.

Why this exists: error messages drift across versions but ops teams
need a way to grep for known failure modes without parsing free-text.
A `DIG_E_NNNN` code in the log line + the HTTP response gives that.

Vocabulary discipline:
  - Codes are immutable once shipped. New codes are appended; codes
    are never reused even if the original meaning is retired.
  - The first digit groups the area:
      1xxx — engine / executor
      2xxx — storage / persistence
      3xxx — connectors / IO
      4xxx — packs / plugin loader
      5xxx — auth / multi-user
      6xxx — runtime / lifecycle
      9xxx — internal / unexpected
  - Codes 1000 → 1999 are reserved for the engine. Steps emit them
    via `raise DigError(ErrorCode.E_1002_TEMPLATE_RENDER_FAILED, ...)`.

Operators get the canonical list at docs/ERROR_CODES.md (auto-generated).
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Stable codes that surface in logs + API errors. Each value is the literal grep token."""

    # --- 1xxx — engine / executor ---------------------------------------
    E_1001_PIPELINE_VALIDATION_FAILED = "DIG_E_1001"
    E_1002_TEMPLATE_RENDER_FAILED     = "DIG_E_1002"
    E_1003_STEP_EXECUTION_FAILED      = "DIG_E_1003"
    E_1004_CAST_FAILURE               = "DIG_E_1004"
    E_1005_CYCLE_DETECTED             = "DIG_E_1005"
    E_1006_NAN_PRODUCED               = "DIG_E_1006"
    E_1007_NAN_SCAN_FAILED            = "DIG_E_1007"

    # --- 2xxx — storage / persistence -----------------------------------
    E_2001_DB_INIT_FAILED             = "DIG_E_2001"
    E_2002_SCHEMA_PATCH_FAILED        = "DIG_E_2002"
    E_2003_RUN_NOT_FOUND              = "DIG_E_2003"
    E_2004_PIPELINE_NOT_FOUND         = "DIG_E_2004"
    E_2005_DATASET_NOT_FOUND          = "DIG_E_2005"
    E_2006_ETAG_MISMATCH              = "DIG_E_2006"

    # --- 3xxx — connectors / IO -----------------------------------------
    E_3001_CONNECTOR_UNKNOWN          = "DIG_E_3001"
    E_3002_CONNECTOR_READ_FAILED      = "DIG_E_3002"
    E_3003_CONNECTOR_WRITE_FAILED     = "DIG_E_3003"
    E_3004_PATH_ESCAPE                = "DIG_E_3004"
    E_3005_SSRF_BLOCKED               = "DIG_E_3005"

    # --- 4xxx — packs / plugin loader -----------------------------------
    E_4001_PACK_VALIDATION_FAILED     = "DIG_E_4001"
    E_4002_PACK_INSTALL_FAILED        = "DIG_E_4002"
    E_4003_PACK_DEPENDENCY_REJECTED   = "DIG_E_4003"
    E_4004_STEP_REGISTRATION_FAILED   = "DIG_E_4004"

    # --- 5xxx — auth / multi-user -------------------
    E_5001_AUTH_REQUIRED              = "DIG_E_5001"
    E_5002_AUTH_INVALID               = "DIG_E_5002"
    E_5003_AUTHZ_DENIED               = "DIG_E_5003"

    # --- 6xxx — runtime / lifecycle -------------------------------------
    E_6001_RUN_ABORTED                = "DIG_E_6001"
    E_6002_BODY_TOO_LARGE             = "DIG_E_6002"
    E_6003_RATE_LIMITED               = "DIG_E_6003"
    E_6004_WS_FRAME_TOO_LARGE         = "DIG_E_6004"

    # --- 9xxx — internal / unexpected -----------------------------------
    E_9001_INTERNAL                   = "DIG_E_9001"
    E_9002_NOT_IMPLEMENTED            = "DIG_E_9002"


class DigError(Exception):
    """Standard exception carrying a stable error code + context.

    Raise this anywhere a known failure mode applies. Catch sites pass
    `e.code.value` to logger.error(..., extra={"error_code": code}) so
    the structured-log formatter picks it up automatically.
    """

    def __init__(self, code: ErrorCode, message: str, *, context: dict | None = None) -> None:
        self.code = code
        self.context = context or {}
        super().__init__(f"{code.value}: {message}")

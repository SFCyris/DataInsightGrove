#!/usr/bin/env python3
"""Regenerate docs/ERROR_CODES.md from the ErrorCode enum.

Run after adding a new ErrorCode value:

    python3 scripts/gen-error-codes-doc.py

The generated doc is committed so contributors can search it without
running the script. Treat the script as authoritative; never hand-edit
the .md.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "backend" / "dig" / "observability" / "error_codes.py"
TARGET = REPO_ROOT / "docs" / "ERROR_CODES.md"


# Group label per leading digit. Mirrors the comment block in error_codes.py.
GROUP_LABELS = {
    "1": "Engine / executor",
    "2": "Storage / persistence",
    "3": "Connectors / IO",
    "4": "Packs / plugin loader",
    "5": "Auth / multi-user",
    "6": "Runtime / lifecycle",
    "9": "Internal / unexpected",
}


def _import_error_code() -> type:
    """Import ErrorCode without dragging in the full dig package (which would
    require the venv to be the active interpreter)."""
    spec = importlib.util.spec_from_file_location("error_codes", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SOURCE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ErrorCode


# Hand-curated meanings — keep in sync with the ErrorCode enum.
# Empty string means "fall back to the auto-humanised form".
_MEANINGS: dict[str, str] = {
    "DIG_E_1001": "Pipeline document failed schema or DAG validation.",
    "DIG_E_1002": "{{ }} template render raised an error (bad var, filter, or path-safety violation).",
    "DIG_E_1003": "A step's `execute_polars` raised an unhandled exception.",
    "DIG_E_1004": "TRY_CAST returned NULL for non-NULL source values (string→number, malformed date, etc.).",
    "DIG_E_1005": "Sub-pipeline reference forms a cycle (P references its own ancestor).",
    "DIG_E_1006": "A step computation produced NaN or ±Inf in a float column (sidecar attached).",
    "DIG_E_1007": "Post-step NaN scanner raised; sidecar omitted, output still coerced.",
    "DIG_E_2001": "init_db() failed (DB unreachable, permissions, or corrupt schema).",
    "DIG_E_2002": "Additive ALTER TABLE patch failed (duplicate column, FK lock, …).",
    "DIG_E_2003": "Run id not found in the runs table.",
    "DIG_E_2004": "Pipeline id not found in the pipelines table.",
    "DIG_E_2005": "Dataset id not found in the datasets table.",
    "DIG_E_2006": "Save/update rejected: client's etag doesn't match the server's current row.",
    "DIG_E_3001": "Connector id is not registered.",
    "DIG_E_3002": "Connector read failed (network, auth, format).",
    "DIG_E_3003": "Connector write/sink failed.",
    "DIG_E_3004": "Path escapes the allowed roots (data_dir + samples/) without DIG_LOCAL_FILE_ALLOW_ABSOLUTE.",
    "DIG_E_3005": "Outbound URL blocked by the SSRF allowlist (private/loopback/link-local).",
    "DIG_E_4001": "Pack manifest failed JSON Schema validation.",
    "DIG_E_4002": "Pack auto-install via pip failed.",
    "DIG_E_4003": "Pack `pythonRequirements` entry rejected by the strict PEP-508 allowlist.",
    "DIG_E_4004": "A step in a pack failed to register at load time.",
    "DIG_E_5001": "Request requires authentication (DIG_AUTH_TOKEN set, none supplied).",
    "DIG_E_5002": "Authentication token did not match.",
    "DIG_E_5003": "Authenticated user is not authorised for this action (Enterprise-tier RBAC).",
    "DIG_E_6001": "Run was aborted (cancellation, shutdown, or operator request).",
    "DIG_E_6002": "Request body exceeds DIG_MAX_BODY_BYTES.",
    "DIG_E_6003": "Request rate-limited.",
    "DIG_E_6004": "WebSocket frame exceeds DIG_WS_MAX_BYTES.",
    "DIG_E_9001": "Internal error — please open a GitHub issue with the full traceback.",
    "DIG_E_9002": "Surface or feature not yet implemented in this tier.",
}


def _humanise(value: str, name: str) -> str:
    """Prefer the curated meaning; fall back to ID-derived title-case."""
    curated = _MEANINGS.get(value, "").strip()
    if curated:
        return curated
    parts = name.split("_", 2)
    if len(parts) >= 3:
        return parts[2].replace("_", " ").capitalize()
    return name.replace("_", " ").capitalize()


def main() -> None:
    ErrorCode = _import_error_code()

    by_group: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for code in ErrorCode:
        # E_1004_CAST_FAILURE → first digit "1"
        m = re.match(r"E_(\d)\d+_", code.name)
        if not m:
            continue
        first = m.group(1)
        by_group[first].append((code.value, code.name, _humanise(code.value, code.name)))

    out = ["# ⚠️ Error codes",
           "",
           "DIG raises stable `DIG_E_NNNN` codes that surface in logs and "
           "API error responses. Search this page for the code your operator "
           "saw to find the canonical meaning + remediation hint.",
           "",
           "_This page is auto-generated from "
           "`backend/dig/observability/error_codes.py` via "
           "`scripts/gen-error-codes-doc.py`. Do not hand-edit._",
           "",
           "## Promise",
           "",
           "- Codes are **immutable** once shipped. New codes are appended; "
           "codes are never reused even if the original meaning is retired.",
           "- The first digit of `NNNN` groups the area (1xxx engine, 2xxx "
           "storage, 3xxx connectors, 4xxx packs, 5xxx auth, 6xxx runtime, "
           "9xxx internal).",
           "- All codes appear in:",
           "  - structured log lines (`{\"error_code\": \"DIG_E_1004\", ...}` "
           "when `DIG_LOG_FORMAT=json`)",
           "  - `DigError.__str__` output",
           "  - HTTP error response bodies (`error_code` field, when set)",
           ""]

    for digit in sorted(by_group):
        label = GROUP_LABELS.get(digit, f"Group {digit}xxx")
        out.append(f"## {digit}xxx — {label}")
        out.append("")
        out.append("| Code | Identifier | Meaning |")
        out.append("|------|------------|---------|")
        for value, name, human in sorted(by_group[digit]):
            out.append(f"| `{value}` | `{name}` | {human} |")
        out.append("")

    out.extend([
        "## Adding a new code",
        "",
        "1. Pick the next free integer in the right area (don't reuse retired codes).",
        "2. Add the entry to `ErrorCode` in "
        "`backend/dig/observability/error_codes.py`.",
        "3. Run `python3 scripts/gen-error-codes-doc.py` to refresh this file.",
        "4. Reference the code at every raise site via `raise DigError("
        "ErrorCode.E_NNNN_X, message, context={...})`.",
        "5. Commit both changes.",
        "",
        "## See also",
        "",
        "- [`backend/dig/observability/error_codes.py`](../backend/dig/observability/error_codes.py) "
        "— the `ErrorCode` enum (source of truth)",
        "- [`SECURITY.md`](../SECURITY.md) — what failure modes have stable codes vs free-text",
        "",
    ])

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO_ROOT)} ({len(by_group)} groups, "
          f"{sum(len(v) for v in by_group.values())} codes)")


if __name__ == "__main__":
    main()

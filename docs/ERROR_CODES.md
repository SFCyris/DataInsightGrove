# ⚠️ Error codes

DIG raises stable `DIG_E_NNNN` codes that surface in logs and API error responses. Search this page for the code your operator saw to find the canonical meaning + remediation hint.

_This page is auto-generated from `backend/dig/observability/error_codes.py` via `scripts/gen-error-codes-doc.py`. Do not hand-edit._

## Promise

- Codes are **immutable** once shipped. New codes are appended; codes are never reused even if the original meaning is retired.
- The first digit of `NNNN` groups the area (1xxx engine, 2xxx storage, 3xxx connectors, 4xxx packs, 5xxx auth, 6xxx runtime, 9xxx internal).
- All codes appear in:
  - structured log lines (`{"error_code": "DIG_E_1004", ...}` when `DIG_LOG_FORMAT=json`)
  - `DigError.__str__` output
  - HTTP error response bodies (`error_code` field, when set)

## 1xxx — Engine / executor

| Code | Identifier | Meaning |
|------|------------|---------|
| `DIG_E_1001` | `E_1001_PIPELINE_VALIDATION_FAILED` | Pipeline document failed schema or DAG validation. |
| `DIG_E_1002` | `E_1002_TEMPLATE_RENDER_FAILED` | {{ }} template render raised an error (bad var, filter, or path-safety violation). |
| `DIG_E_1003` | `E_1003_STEP_EXECUTION_FAILED` | A step's `execute_polars` raised an unhandled exception. |
| `DIG_E_1004` | `E_1004_CAST_FAILURE` | TRY_CAST returned NULL for non-NULL source values (string→number, malformed date, etc.). |
| `DIG_E_1005` | `E_1005_CYCLE_DETECTED` | Sub-pipeline reference forms a cycle (P references its own ancestor). |
| `DIG_E_1006` | `E_1006_NAN_PRODUCED` | A step computation produced NaN or ±Inf in a float column (sidecar attached). |
| `DIG_E_1007` | `E_1007_NAN_SCAN_FAILED` | Post-step NaN scanner raised; sidecar omitted, output still coerced. |

## 2xxx — Storage / persistence

| Code | Identifier | Meaning |
|------|------------|---------|
| `DIG_E_2001` | `E_2001_DB_INIT_FAILED` | init_db() failed (DB unreachable, permissions, or corrupt schema). |
| `DIG_E_2002` | `E_2002_SCHEMA_PATCH_FAILED` | Additive ALTER TABLE patch failed (duplicate column, FK lock, …). |
| `DIG_E_2003` | `E_2003_RUN_NOT_FOUND` | Run id not found in the runs table. |
| `DIG_E_2004` | `E_2004_PIPELINE_NOT_FOUND` | Pipeline id not found in the pipelines table. |
| `DIG_E_2005` | `E_2005_DATASET_NOT_FOUND` | Dataset id not found in the datasets table. |
| `DIG_E_2006` | `E_2006_ETAG_MISMATCH` | Save/update rejected: client's etag doesn't match the server's current row. |

## 3xxx — Connectors / IO

| Code | Identifier | Meaning |
|------|------------|---------|
| `DIG_E_3001` | `E_3001_CONNECTOR_UNKNOWN` | Connector id is not registered. |
| `DIG_E_3002` | `E_3002_CONNECTOR_READ_FAILED` | Connector read failed (network, auth, format). |
| `DIG_E_3003` | `E_3003_CONNECTOR_WRITE_FAILED` | Connector write/sink failed. |
| `DIG_E_3004` | `E_3004_PATH_ESCAPE` | Path escapes the allowed roots (data_dir + samples/) without DIG_LOCAL_FILE_ALLOW_ABSOLUTE. |
| `DIG_E_3005` | `E_3005_SSRF_BLOCKED` | Outbound URL blocked by the SSRF allowlist (private/loopback/link-local). |

## 4xxx — Packs / plugin loader

| Code | Identifier | Meaning |
|------|------------|---------|
| `DIG_E_4001` | `E_4001_PACK_VALIDATION_FAILED` | Pack manifest failed JSON Schema validation. |
| `DIG_E_4002` | `E_4002_PACK_INSTALL_FAILED` | Pack auto-install via pip failed. |
| `DIG_E_4003` | `E_4003_PACK_DEPENDENCY_REJECTED` | Pack `pythonRequirements` entry rejected by the strict PEP-508 allowlist. |
| `DIG_E_4004` | `E_4004_STEP_REGISTRATION_FAILED` | A step in a pack failed to register at load time. |

## 5xxx — Auth / multi-user

| Code | Identifier | Meaning |
|------|------------|---------|
| `DIG_E_5001` | `E_5001_AUTH_REQUIRED` | Request requires authentication (DIG_AUTH_TOKEN set, none supplied). |
| `DIG_E_5002` | `E_5002_AUTH_INVALID` | Authentication token did not match. |
| `DIG_E_5003` | `E_5003_AUTHZ_DENIED` | Authenticated user is not authorised for this action (Enterprise-tier RBAC). |

## 6xxx — Runtime / lifecycle

| Code | Identifier | Meaning |
|------|------------|---------|
| `DIG_E_6001` | `E_6001_RUN_ABORTED` | Run was aborted (cancellation, shutdown, or operator request). |
| `DIG_E_6002` | `E_6002_BODY_TOO_LARGE` | Request body exceeds DIG_MAX_BODY_BYTES. |
| `DIG_E_6003` | `E_6003_RATE_LIMITED` | Request rate-limited. |
| `DIG_E_6004` | `E_6004_WS_FRAME_TOO_LARGE` | WebSocket frame exceeds DIG_WS_MAX_BYTES. |

## 9xxx — Internal / unexpected

| Code | Identifier | Meaning |
|------|------------|---------|
| `DIG_E_9001` | `E_9001_INTERNAL` | Internal error — please open a GitHub issue with the full traceback. |
| `DIG_E_9002` | `E_9002_NOT_IMPLEMENTED` | Surface or feature not yet implemented in this tier. |

## Adding a new code

1. Pick the next free integer in the right area (don't reuse retired codes).
2. Add the entry to `ErrorCode` in `backend/dig/observability/error_codes.py`.
3. Run `python3 scripts/gen-error-codes-doc.py` to refresh this file.
4. Reference the code at every raise site via `raise DigError(ErrorCode.E_NNNN_X, message, context={...})`.
5. Commit both changes.

## See also

- [`backend/dig/observability/error_codes.py`](../backend/dig/observability/error_codes.py) — the `ErrorCode` enum (source of truth)
- [`SECURITY.md`](../SECURITY.md) — what failure modes have stable codes vs free-text

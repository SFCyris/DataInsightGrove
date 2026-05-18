# ⚙️ Configuration reference

Every `DIG_*` environment variable, what it does, what type of value it
accepts, and where in the codebase to find the implementation.

> **Looking for the JSON config file?** As of 1.0 DIG also reads a
> persistent JSON config at `~/.config/dig/config.json` (managed via
> `./scripts/dig_config.py`). Env vars still work and **override** the
> file. The file's full schema, the precedence rules, and the on-disk
> layout for an operator are documented in
> [`ADMINISTRATION.md`](ADMINISTRATION.md). This page focuses on every
> individual env var.

Set the variables you need in your shell, in a systemd unit, in a
`.env` file your shell sources, or via the Mac .app / Linux .desktop
wrappers.

---

## Quick start — what most users actually need

| Variable | Default | When to set it |
|---|---|---|
| `DIG_AUTH_TOKEN` | _(unset)_ | Any non-loopback exposure. Strongly recommended. |
| `DIG_DATA_DIR` | `<repo>/data/` (the dev / OSS-checkout default; resolved by `backend/dig/storage/files.py`) | Move user data to a different disk, or unify multiple checkouts onto one shared dir |
| `DIG_API_PORT` | `8090` | Port collision with another tool |
| `DIG_WEB_PORT` | `3000` | Same |
| `DIG_LOG_FORMAT` | _(unset; emits text)_ | Set to `json` for production deployments piping logs into Loki / Datadog / Splunk. Only `json` is honoured — `text` / anything else / unset all keep the friendly developer format. |

Everything else is power-user / operations territory.

---

## Network + binding

| Variable | Default | Notes |
|---|---|---|
| `DIG_API_HOST` (alias: `DIG_HOST`) | `127.0.0.1` | Backend bind address. `0.0.0.0` for LAN exposure (combine with `DIG_AUTH_TOKEN`). |
| `DIG_API_PORT` (alias: `DIG_PORT`) | `8090` | Backend port. |
| `DIG_WEB_HOST` | `127.0.0.1` | Frontend dev-server bind address. |
| `DIG_WEB_PORT` | `3000` | Frontend port. |
| `NEXT_PUBLIC_DIG_API` | _(derived)_ | **Frontend-only build-time override** for the API base URL (e.g. `http://localhost:8090`). The backend itself never reads this; the frontend bundle bakes it in via Next.js's `NEXT_PUBLIC_` convention. Set when the frontend is served behind a reverse proxy and the API lives at a non-default host. |
| `DIG_CORS_ORIGINS` | _(loopback only)_ | Comma-separated list of additional origins allowed by CORS. Prefer leaving unset; if you need cross-origin access, gate it via `DIG_AUTH_TOKEN`. |

## Authentication

| Variable | Default | Notes |
|---|---|---|
| `DIG_AUTH_TOKEN` | _(unset)_ | When set, every API + WebSocket request must present `Authorization: Bearer <token>` (or `?token=` for WebSocket). Compared via `secrets.compare_digest`. **Required for any non-loopback exposure.** |

## Storage

| Variable | Default | Notes |
|---|---|---|
| `DIG_DATA_DIR` | `<repo>/data/` | Root of all user data: `dig.sqlite`, `outputs/`, `extensions/`, `.installed_version`. Move this to a faster disk for big workloads, or to a shared dir if you operate multiple checkouts. |
| `DIG_DB_PATH` | `<DIG_DATA_DIR>/dig.sqlite` | Override for the SQLite file location specifically. |
| `DIG_DB_ECHO` | `0` | Set to `1` to log every SQL statement SQLAlchemy executes. Noisy; debug only. |
| `DIG_LOG_DIR` | `$TMPDIR` (or `/tmp` if unset) | Where the lifecycle wrapper writes `dig-api.log` / `dig-web.log`. The default is the OS temp dir; set this to a persistent location (e.g. `<DIG_DATA_DIR>/logs`) if you want logs to survive reboots. |
| `DIG_LOCAL_FILE_ALLOW_ABSOLUTE` | `0` | Opt-in escape from the local-file path confinement. Set to `1` to let DIG ingest any file the process can read. **Risky** — only enable if you understand the implication. See [`SECURITY.md`](../SECURITY.md). |
| `DIG_EXPORT_ALLOW_ABSOLUTE` | `0` | Same shape, for output sinks that write to absolute paths. |

## Resource limits

| Variable | Default | Notes |
|---|---|---|
| `DIG_MAX_BODY_BYTES` | `33554432` (32 MiB) | HTTP request body cap. Returns 413 when exceeded. Raise for unusually large pipeline imports. |
| `DIG_MAX_UPLOAD_MB` | `500` | Cap on dataset uploads via the upload endpoint. |
| `DIG_MAX_DATASET_MB` | `65536` (64 GiB) | Cap on in-memory size of a single ingested dataset. Aligns with the "up to ~50 GB" claim; raise further for larger sources, or lower to enforce a tighter ceiling on shared hosts. |
| `DIG_MAX_PIPELINE_KB` | `2048` (2 MiB) | Cap on pipeline-document size at save / import. Pipelines this large usually indicate accidentally-pasted data. |
| `DIG_WS_MAX_BYTES` | `1048576` (1 MiB) | WebSocket frame cap. Keeps a runaway publisher from OOM'ing the server. |
| `DIG_VALIDATE_MAX_NODES` | `300` | `/validate` per-node compile probe cap. Pipelines with more nodes skip the probe. |
| `DIG_PIPELINE_HISTORY_MAX` | `50` | Per-pipeline snapshot retention. Older snapshots expire on next save. |
| `DIG_FRESHNESS_CACHE_SIZE` | `50000` | LRU cache size for the freshness scanner. Raise for very large catalogs. |

## Observability

| Variable | Default | Notes |
|---|---|---|
| `DIG_LOG_FORMAT` | _(text)_ | Set to `json` to emit one-line JSON per log record. Picks up structured `extra` fields (run_id, node_id, error_code, etc.) automatically. See [`docs/ERROR_CODES.md`](ERROR_CODES.md). |
| `DIG_LOG_LEVEL` | `INFO` | Standard Python `logging` level — `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

## AI assistant + outbound HTTP

| Variable | Default | Notes |
|---|---|---|
| `DIG_AI_ALLOW_PRIVATE` | `0` | By default the AI plugin blocks calls to RFC1918 private addresses. Set `1` to allow (e.g. for a local Ollama on `192.168.1.x`). |
| `DIG_REST_ALLOW_PRIVATE` | `0` | Same gate, for the REST/HTTPS connector. SSRF protection — leave off unless you have an internal API to talk to. |

## Pack installation

| Variable | Default | Notes |
|---|---|---|
| `DIG_PACK_AUTO_INSTALL_DEPS` | `1` | When set to `0` / `false` / `no` / `off`, pack `pythonRequirements` are NOT auto-installed. Operator runs `pip install` themselves. |
| `DIG_PIP_INDEX_URL` | `https://pypi.org/simple/` | Override the pip index pack auto-install reads from. Point at a corporate / mirrored index to control supply chain. |

## Scheduling + templates

| Variable | Default | Notes |
|---|---|---|
| `DIG_SCHED` | _(crontab marker)_ | Marker token used in the user's crontab to identify DIG-managed cron entries (`# DIG_SCHED:<pipeline_id>`). Don't change in production — DIG looks for this exact token to find its rows. |
| `DIG_TEMPLATE_REVIEW` | `manual` | Template approval mode for the AI-generated step / connector review path. |

## Development

| Variable | Default | Notes |
|---|---|---|
| `DIG_RELOAD` | `0` | Set to `1` to enable uvicorn auto-reload in dev. Off in production. |

---

## How DIG resolves these

Most variables are read directly via `os.environ.get(...)` at the point
of use, with sensible defaults. A few network-related ones (`DIG_API_*`,
`DIG_WEB_*`, `DIG_HOST`, `DIG_PORT`) are resolved through
[`backend/dig/_settings.py`](../backend/dig/_settings.py), which
implements a small precedence chain:

```
1. Process env vars           (highest priority)
2. Aliases (DIG_HOST → DIG_API_HOST, DIG_PORT → DIG_API_PORT)
3. Hard-coded defaults        (lowest priority)
```

For the lifecycle wrappers (Mac .app, Linux .desktop), variables
exported in your shell are inherited by the wrapped process. See
[`docs/lifecycle.md`](lifecycle.md) for the wrapper-specific
configuration story.

---

## Adding a new env var

When you add a `DIG_*` variable to the codebase:

1. Read it via `os.environ.get("DIG_NEW_VAR", "<default>")` near the
   point of use.
2. Add a row to the right table above.
3. If it's security-relevant, add a row to [`SECURITY.md`](../SECURITY.md)
   under "Known security-relevant configuration".
4. Don't bury it in a global module-level constant — the value should
   be re-read on each startup, not frozen at import time. Tests need
   to be able to override via `monkeypatch.setenv`.

---

## See also

- [`SECURITY.md`](../SECURITY.md) — security implications of
  `DIG_LOCAL_FILE_ALLOW_ABSOLUTE`, `DIG_AUTH_TOKEN`, etc.
- [`docs/ERROR_CODES.md`](ERROR_CODES.md) — what `DIG_LOG_FORMAT=json`
  surfaces as `error_code` in the structured payload
- [`docs/UPGRADING.md`](UPGRADING.md) — how `DIG_DATA_DIR` interacts
  with the `data/.installed_version` marker
- [`docs/lifecycle.md`](lifecycle.md) — start / stop / status, plus
  Mac .app / Linux .desktop env-var wiring

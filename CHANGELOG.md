# Changelog

All notable changes to DataInsightGrove are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/) once 1.0.0 ships. Pre-1.0 releases may include breaking changes between minor versions.

## [1.0.0] — 2026-07-17

First stable release of the 1.0 line. Graduates 1.0.0-rc3 with a faster
live-preview engine, an expanded FunctionPacks library, a default-port
change, and a streamlined install/start/stop flow.

### Added

- **FunctionPacks library** — additional bundled packs (including text/NLP)
  plus a broader set of example flows and templates under
  `FunctionPacks/examples` and `FunctionPacks/templates`.
- **Preview materialization cache** — Polars-engine ancestors of a focused
  node are fingerprinted and reused across canvas focuses, so re-visiting a
  step no longer recomputes the upstream chain. Deterministic steps only;
  non-deterministic steps always re-run. Preview caches are cleared on boot.
- Backend regression tests for AI streaming, dataset refresh, pack upload,
  and the preview / materialization paths.

### Changed

- **Default ports** — the API now listens on **8190** and the web UI on
  **3100** (were 8090 / 3000). Override with `DIG_API_PORT` / `DIG_WEB_PORT`,
  `~/.config/dig/config.json`, or the `--api-port` / `--web-port` flags.
- **Quickstart** — install, start, and stop are now three explicit commands
  (`./install.sh`, `./start.sh`, `./stop.sh`) in the README and getting-started guide.

### Fixed

- Development `--reload` mode starts cleanly and scopes its file watcher to
  the backend source, so editor saves no longer cold-restart the worker.

## [1.0.0-rc3] — 2026-05-18

Third release candidate of the 1.0 line. Combines the round-4 / round-5
workflow + interaction polish with the release-prep wave (TLS dual-
protocol, input-data preservation policy, geospatial pack expansion,
50 GB-on-a-single-host validation).

### Added — release-prep wave

- **TLS dual-protocol**: HTTPS is available via a TLS-terminating proxy on
  parallel ports (default 8443 / 3443) alongside the HTTP listeners. The
  page-to-API path uses same-origin via a Next.js `/api/*` rewrite, so no
  cert trust install is required for the UI to work.
- **Rotating logs**: API + web + TLS-proxy streams write through a
  `RotatingFileHandler` wrapper to `/var/log/DIG` (bootstrapped with sudo
  on first run; falls back to `~/Library/Logs/DIG` on macOS or
  `~/.local/state/DIG/logs` on Linux). Size + count configurable via
  `log.maxBytes` / `log.backupCount` (defaults: 10 MB × 5 files).
- **Startup banner**: every boot writes a structured banner to the top of
  the active log file — version, git SHA, OS, kernel, Python, Node, CPU,
  RAM, disk free, resolved config, masked `DIG_*` env vars.
- **Once-and-done auto-trust**: cert install into the system trust store
  is attempted exactly once; subsequent restarts skip the sudo prompt
  whether successful or declined. Re-trigger explicitly with
  `./scripts/dig_tls.py trust`.
- **Geospatial pack**: dual-resolution world atlas (10m + 110m);
  auto-resolution by bbox-diagonal heuristic; dot-proxy substitution at
  world scale (HTML re-evaluates on zoom); Mercator-aligned PNG
  choropleth; EU GDP + SF Bay Area demo pipelines.
- **Reference existing file**: new modal + canvas dropdown footer entry
  registers an existing file as a dataset reference without copying it
  into DIG's managed area.
- **Settings UI — Server & TLS tab**: 7 boot-time entries (log dir, log
  rotation, TLS toggles, HTTPS ports) round-trip through
  `~/.config/dig/config.json`.
- **ADMINISTRATION.md**: new operator-facing reference covering the
  config-file schema, product tree, on-disk folder layout, log rotation,
  and backup boundaries.
- **50 GB benchmark**: `scripts/_gen_50gb_dataset.py` +
  `scripts/_run_benchmark.py` — end-to-end driver runs a 5-step pipeline
  with 6 terminals (3 file outputs + 3 visualisations) against a 500 M-row
  dataset.

### Changed — release-prep wave

- **Input data is sacred**: `DELETE /api/datasets/{id}` removes only the
  DB row + DIG's internal Parquet cache. Source files at `source_uri` are
  preserved regardless of location (`data/uploads/`, `data/inputs/`,
  anywhere else). Audit log surfaces every preserved path.
- **`DIG_MAX_DATASET_MB` default raised** from 1024 → 65 536 (64 GB) to
  align with the documented "up to ~50 GB on a single dataset" claim.
- **`Pipeline.stepVersion`** is now optional on the wire — missing values
  are backfilled at parse time from the live registry version.
- **`.gitignore`** sanitised.
- **Variables demo sink**: `file://exports/...` parsed as authority +
  absolute path and was rejected by `assert_local_path_safe`; replaced
  with the run-output-relative default.

### Configuration

- New `~/.config/dig/config.json` blocks: `api.httpsPort`,
  `web.httpsPort`, `log.{maxBytes,backupCount}`, and
  `tls.{enabled,certFile,keyFile,autoTrust,additionalSans}`. JSON Schema
  + CONFIG.md updated to match.
- Boot-time settings registered in the backend Settings registry with
  `source: "config_file"` so writes round-trip to disk and the UI can
  show a "(requires restart)" hint.

### Fixed — release-prep wave

- Gallery template detail page: `q.data?.name` → `q.data?.title` (the
  API field is `title`).
- macOS `Info.plist` version: bumped from the placeholder 0.0.1 to 1.0.0.

### Added — workflow polish wave (formerly Unreleased)

- **Command palette**: per-pipeline verbs (▶ run, 📑 duplicate, ⏰ schedule, 🔗 copy link, ⬇ export), Recent group at the top of the palette, "New blank pipeline" / "Browse templates" / "Upload a dataset" create-flow shortcuts, and a global `/` shortcut that focuses the palette search. Typing a step name while inside the editor now inserts it; previously the palette only toasted a hint.
- **G-chord navigation**: `g h` / `g p` / `g d` / `g r` / `g c` / `g s` jump to Home / Pipelines / Datasets / Runs / Catalog / Settings (Linear / GitHub convention). 1-second timeout; disarmed silently if the second key isn't mapped.
- **Recent items**: `localStorage`-backed FIFO of the last 10 pipelines + 10 datasets, populated automatically on every open. Surfaces on the home page (when present) and at the top of the command palette.
- **Favorites / pinning**: ⭐ on every pipeline card; pinned items sort to the top of the list and read with a `⭐` prefix in the palette.
- **Run cancel**: new `POST /runs/{id}/cancel` endpoint + a 🛑 Stop button that replaces ▶ Run while a run is in flight. CancelledError now flips Run status to `cancelled` (separate from `failed`) and fires webhooks + events for the new state.
- **Split-button sample picker**: run-on-sample sizes (1k / 10k / 100k / 1M / full) sit flush with the Run button — picking a size for a one-off no longer dirties the pipeline doc.
- **Run-detail → editor focus jump**: failed runs build `?focus=<nodeId>` links; the editor now consumes that param on mount, scrolls to the failing node, then clears the URL.
- **WS reattach on reload**: refreshing the editor mid-run re-subscribes to the in-flight WebSocket instead of going dark.
- **Multi-file dataset upload**: dropzone accepts an arbitrary number of files at once; each becomes its own dataset. On success, a "Imported N datasets" toast offers a one-click jump to the catalog (the natural place to join them).
- **Dataset name conflict**: backend now returns 409 with `{ code: "dataset_name_in_use", existingId }` when uploading a dataset whose name already exists. Frontend resolves into a sonner confirm: **Replace** (re-ingest in place, keep the dataset ID) / **Keep both** / Cancel. Set `on_name_conflict=allow` to opt out of the prompt.
- **Dataset refresh**: new `POST /datasets/{id}/refresh` endpoint + a 🔄 Refresh button on the dataset detail header. Re-runs the connector against the existing `source_uri` and preserves the dataset_id so downstream pipelines stay attached. The failed-ingest panel now also offers Retry.
- **Variable templating hint at ingest**: the REST-connector URL field surfaces `{{ today }}` / `{{ now }}` / `{{ vars.region }}` inline with a link to `docs/VARIABLES.md`.
- **Notification rule dry-run**: `POST /notification-rules/test` replays a rule's `event_kind` + filters against the last N events. Rule editor gains a 🧪 panel that surfaces "M of N events would have fired this rule" so authors can preview before save.
- **Notification deep-links**: when an event carries `run_id` / `pipeline_id` in its context, the inbox row surfaces 🔍 Run / 🛤 Pipeline links — no more copying ULIDs out of the foldable JSON.
- **Running-count chip on home**: pulses while any pipeline is running anywhere in the workspace; clicking opens the runs grid filtered to queued + running.
- **Multi-tab guard**: a `BroadcastChannel` heartbeat warns when the same pipeline is open in two tabs.
- **Editor keyboard shortcuts**: `⌫` / `Delete` deletes selected nodes via ReactFlow's native `deleteKeyCode`. Double-clicking a sub-pipeline node opens its source in a new tab.
- **Editor before-unload guard**: closing the tab with unsaved keystrokes shows the browser's "leave site?" prompt; clears as soon as the 500ms autosave succeeds.
- **Step picker**: query persists across reopens via sessionStorage; AI ribbon stays visible regardless of query; "✨ Generate a custom step" link lives at the bottom of the picker; the toast after adding a step lists any required-but-undefaulted params (e.g. join's `keys`).
- **MiniMap interactions**: clicking a node in the mini-map selects it in the main canvas; mask + stroke colours now follow the theme tokens instead of being hard-coded light.
- **Run-history popover**: ARIA `role="listbox"`, ticking duration for in-flight runs, and a "See all N runs →" link when the cap of 25 truncates.
- **Settings search**: an in-page search input filters the sidebar by label / help / id.
- **Notification inbox**: timestamps render in local time with the UTC value in `title=`; table wrapper has `role="log" aria-live="polite"`.

### Backend

- `JobManager` honours a `_shutting_down` flag so submissions arriving mid-cancel are rejected with 503 instead of leaking past the shutdown.
- `Pipeline.id` Pydantic constraint (`min_length=1`, `max_length=64`, `[A-Za-z0-9_:-]`) — previously any string.
- `dq_drift` skips anomaly emission when historical mean < 1 (zero-baseline pipelines no longer noisy on every recovery).
- `PipelineHistory` snapshot caps document size at 512 KiB.
- `discard_staged` validates pack version + `.resolve()` containment.
- AI safety lint resolves `from X import Y as Z` aliases, walrus operators, and plain reassignments before testing against the banned-names set. Also rejects metaclasses + `__init_subclass__` / `__set_name__` / `__class_getitem__`.
- Extension entry-point loads have a 10s deadline; manifest depth + item count capped (32 / 10,000).
- `/metrics`: NaN/inf observations rejected (and counted in `dig_metric_observations_dropped_total`), negative counter increments rejected, special floats render as Prometheus-spec `+Inf` / `-Inf` / `NaN`, and the metric-name space is process-wide-capped at 1,000.
- `/health` redacts extension package + version + path for unauthenticated callers.
- Cron list parsing uses `rfind("# DIG_SCHED:")` + ULID validation so quoted-arg marker hijacks can't spoof pipeline IDs.
- REST connector + webhook dispatch share a `_validate_header_pair` allow-list (rejects CRLF / NUL / control bytes in names + values).
- `upgrade.sh` parses pyproject via `tomllib` instead of regex.

### Changed

- `webhook_trigger` step no longer opens an orphan event loop — it submits to the main API loop via `run_coroutine_threadsafe`. Payload now carries `pipelineId` + `pipelineName`.
- Editor toolbar primary action reads "▶ Run pipeline" (not "Run on backend"); the live grid no longer surfaces a "🌐 via backend" badge. Per the brand rule that processing surface stays transparent.

## [1.0.0-rc2] — 2026-05-11

Audit-driven hardening on top of rc1. No structural change.

- Closed the export_to_map XSS chain, AI/webhook SSRF gaps, and the upgrade.sh heredoc injection.
- Fixed three rc1 regressions: upgrade.sh marker timing, the variables-demo datetime crash, and the path-safety gate having no test coverage.
- Tightened templating, metrics, extension loader, schema-migration race handling.
- Aligned the user-visible version surface and demo-count copy across README + UI + CHANGELOG.
- Regenerated the frontend openapi types so the new `/health.extensions` + `RunOut.nanOrigins` are properly typed.

## [1.0.0-rc1] — 2026-05-11

First release-candidate of the 1.0 line. The structural decisions are
locked: schemas, protocol surface, extension architecture, upgrade
contract, security posture. Soak-test through `rc2+` if needed before
tagging `1.0.0`.

### Added

- State-aware NULL display: missing cells render as `NULL` with a cool-grey-blue background + `◌` icon for "value never existed", or a light-orange background + `⚠` icon for "step computation produced NaN / ±Inf". The orange variant survives exactly one step. Backend exposes `RunOut.nanOrigins` (per-node sidecar with row indices + cause) for downstream tooling.
- Variable templating in dataset URIs, output sink URIs, and a new `add_runtime_column` step. Syntax: `{{ today }}`, `{{ now | strftime('%Y%m%d_%H%M%S') }}`, `{{ vars.region }}`. Sandboxed renderer (not Jinja2 — hand-written, closed filter set). See `docs/VARIABLES.md`.
- New bundled demo pipeline: **`📅 demo · variables — timestamped report`**. Showcases output-URI templating + the new `add_runtime_column` step. Seeded automatically by the home-page **🌱 Try with sample data** button alongside the existing customers / healthcare / housing demos.
- Pre-1.0 schema lockdown: nullable identity/metadata columns on `Run`, `Pipeline`, `Dataset` (`owner_id`, `org_id`, `tenant_id`, `created_by`, `updated_by`, `metadata`, `extensions`); `Run` also gains `triggered_by`, `bytes_scanned`, `compute_seconds`, `cost_usd`. Always NULL in OSS. Closed enums opened to free-form strings: `step.engine.primary`, `webhook.on`, `step.category`. ID regex on dataset / node IDs relaxed to allow hyphens and colons.
- `upgrade.sh` — checks GitHub for the latest release and upgrades the local checkout. Supports `--check`, `--yes`, `--to vX.Y.Z`. Refuses to run on a dirty working tree.
- Startup version transition hook: backend reads `data/.installed_version`, compares to the running package version, and emits a `system.startup` event with `upgrade=true` on a transition. Schema patches in `init_db` are additive and idempotent.
- Out-of-tree extension architecture: `dig.protocols` frozen public surface (23 names, `PROTOCOL_VERSION = (1, 0)`); `dig.extensions` loader scanning four entry-point groups (`dig.plugins`, `dig.steps`, `dig.connectors`, `dig.routers`) + `data/extensions/<name>/` filesystem channel; `/health.extensions[*]` + `/health.protocol_version`; `/ext/<name>/static/*` static-file mount. The deployment shape DIG commits to going forward.
- Observability layer: optional JSON log formatter behind `DIG_LOG_FORMAT=json`; `ErrorCode` vocabulary (`DIG_E_*`) + `DigError`; minimal in-process Prometheus-format metrics registry served at `/metrics`. Pre-declared counters: `dig_runs_total`, `dig_steps_executed_total`, `dig_nan_cells_produced_total`, plus inflight-runs gauge.
- CI workflows: `.github/workflows/test.yml` (pytest + vitest + Next.js build) + `lint.yml` (ruff + mypy + tsc). Per-ref concurrency cancellation.
- Test coverage: 231 backend pytest cases + 29 frontend vitest cases, all passing.
- Public docs: `SECURITY.md`, `CHANGELOG.md`, `docs/VARIABLES.md`, `docs/UPGRADING.md`, `docs/EXTENSIBILITY.md`, `docs/ERROR_CODES.md`, `docs/CONFIG.md`.
- Steps + samples carried over from earlier dev work: `backend/steps/check_data/`, `backend/steps/export_to_map/`, `backend/dig/engine/dq_drift.py`, `backend/dig/api/demo_seeds.py`, `backend/dig/api/search.py`, `frontend/app/runs/`, `frontend/components/pipeline-tags.tsx`, `frontend/lib/use-url-state.ts`, plus the `samples/healthcare-*` and `samples/housing-*` demo data (drives the bundled clinical + map demos).

### Changed

- `webhook.on` is no longer a closed enum (`"always" | "succeeded" | "failed" | "triggered"`). Backwards-compatible: existing values still mean the same thing; vendors / enterprise builds can introduce new triggers without a schemaVersion bump.
- `Health` response shape adds `extensions: list[HealthExtension]` and `protocol_version: tuple[int, int]`. Both are additive — existing clients ignore them.

### Security

- Template renderer uses a hand-written sandbox: no attribute walking, no control flow, no Python `eval`, closed filter set.
- Path rendering enforces cross-OS-forbidden character bans (`:` `*` `?` `"` `<` `>` `|` + control bytes), rejects `..` traversal, and gates absolute paths.
- Extension loader name-validates filesystem extension directories before mounting any static path (rejects traversal / URL-reserved chars / control bytes).

## [0.10.0] — 2026-05-09

Baseline release. See the commit message of `1b986c8` for the full inventory of capabilities, stack, demos, and security posture.

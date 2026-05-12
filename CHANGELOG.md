# Changelog

All notable changes to DataInsightGrove are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/) once 1.0.0 ships. Pre-1.0 releases may include breaking changes between minor versions — see `docs/API_STABILITY.md` for the contract.

## [Unreleased]

## [1.0.0-rc1] — 2026-05-11

First release-candidate of the 1.0 line. The structural decisions are
locked: schemas, protocol surface, extension architecture, upgrade
contract, security posture. Soak-test through `rc2+` if needed before
tagging `1.0.0`.

### Added

- State-aware NULL display: missing cells render as `NULL` with a cool-grey-blue background + `◌` icon for "value never existed", or a light-orange background + `⚠` icon for "step computation produced NaN / ±Inf". The orange variant survives exactly one step. Backend exposes `RunOut.nanOrigins` (per-node sidecar with row indices + cause) for downstream tooling.
- Variable templating in dataset URIs, output sink URIs, and a new `add_runtime_column` step. Syntax: `{{ today }}`, `{{ now | strftime('%Y%m%d_%H%M%S') }}`, `{{ vars.region }}`. Sandboxed renderer (not Jinja2 — hand-written, closed filter set). See `docs/VARIABLES.md`.
- New bundled demo pipeline: **`📅 demo · variables — timestamped report`**. Showcases output-URI templating + the new `add_runtime_column` step. Seeded automatically by the home-page **🌱 Try with sample data** button alongside the existing customers / healthcare / housing demos.
- Pre-1.0 schema lockdown: enterprise-anticipatory nullable columns on `Run`, `Pipeline`, `Dataset` (`owner_id`, `org_id`, `tenant_id`, `created_by`, `updated_by`, `metadata`, `extensions`); `Run` also gains `triggered_by`, `bytes_scanned`, `compute_seconds`, `cost_usd`. Always NULL in OSS. Closed enums opened to free-form strings: `step.engine.primary`, `webhook.on`, `step.category`. ID regex on dataset / node IDs relaxed to allow hyphens and colons.
- `upgrade.sh` — checks GitHub for the latest release and upgrades the local checkout. Supports `--check`, `--yes`, `--to vX.Y.Z`. Refuses to run on a dirty working tree.
- Startup version transition hook: backend reads `data/.installed_version`, compares to the running package version, and emits a `system.startup` event with `upgrade=true` on a transition. Schema patches in `init_db` are additive and idempotent.
- Out-of-tree extension architecture: `dig.protocols` frozen public surface (23 names, `PROTOCOL_VERSION = (1, 0)`); `dig.extensions` loader scanning four entry-point groups (`dig.plugins`, `dig.steps`, `dig.connectors`, `dig.routers`) + `data/extensions/<name>/` filesystem channel; `/health.extensions[*]` + `/health.protocol_version`; `/ext/<name>/static/*` static-file mount. The deployment shape DIG commits to going forward — see `internal/EXTENSION_ARCHITECTURE.md`.
- Observability layer: optional JSON log formatter behind `DIG_LOG_FORMAT=json`; `ErrorCode` vocabulary (`DIG_E_*`) + `DigError`; minimal in-process Prometheus-format metrics registry served at `/metrics`. Pre-declared counters: `dig_runs_total`, `dig_steps_executed_total`, `dig_nan_cells_produced_total`, plus inflight-runs gauge.
- CI workflows: `.github/workflows/test.yml` (pytest + vitest + Next.js build) + `lint.yml` (ruff + mypy + tsc). Per-ref concurrency cancellation.
- Test coverage: 231 backend pytest cases + 29 frontend vitest cases, all passing.
- Public docs: `SECURITY.md`, `CHANGELOG.md`, `docs/API_STABILITY.md`, `docs/VARIABLES.md`, `docs/UPGRADING.md`, `docs/EXTENSIBILITY.md`, `docs/ERROR_CODES.md`, `docs/CONFIG.md`. Internal: `internal/EXTENSION_ARCHITECTURE.md`, updated cross-links from `internal/TIER_ARCHITECTURE.md` + `internal/PLG_AND_ENTERPRISE_STRATEGY.md`.
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

# 🛠 Administration

Operator-facing reference for **deploying, configuring, and maintaining** a
DIG installation. Covers:

- the on-disk **configuration file** (`~/.config/dig/config.json`) — schema,
  precedence, every key
- the **product tree** — what processes DIG runs and how they relate
- the **folder structure** — repo layout *and* runtime layout, so you know
  what to back up, what to migrate, and what to leave alone

If you're *using* DIG (building pipelines), you want
[`getting_started.md`](getting_started.md). If you're *contributing*, you
want [`ARCHITECTURE.md`](ARCHITECTURE.md). This page is for the person who
runs DIG on a server / shared machine / their own workstation and needs to
operate it.

---

## 1. Configuration

### 1.1 Where settings come from

DIG resolves its effective configuration by merging four sources, **in
ascending priority** (later overrides earlier):

| Priority | Source | When you'd use it |
|---|---|---|
| 1 | Hard-coded defaults | The fallback if nothing else is set. |
| 2 | JSON config file | Persistent settings for this install. |
| 3 | Environment variables | Per-process / per-shell overrides; CI; container deployments. |
| 4 | CLI flags (`./scripts/dig-start.sh --api-port 9000 --save`) | One-off testing, or `--save` to persist into the config file. |

The full env-var inventory lives in [`CONFIG.md`](CONFIG.md). This page
focuses on the **config file** — the new source-of-truth that landed in
1.0.

### 1.2 Config file location

The first existing path in this list wins:

1. `$DIG_CONFIG` (if set) — explicit override.
2. `$XDG_CONFIG_HOME/dig/config.json` — defaults to `~/.config/dig/config.json`
   on Linux **and** macOS (we deliberately use the same XDG path on both
   platforms instead of macOS's `~/Library/Application Support/`, so a
   user moving a dotfiles repo between OSes keeps one config).
3. `<repo>/dig.config.json` — only useful when you check a config in
   alongside the source (e.g. for a single-tenant deployment in a private
   git repo).

If no file exists, DIG runs entirely on defaults + env. Create one with:

```bash
./scripts/dig_config.py init             # writes ~/.config/dig/config.json
./scripts/dig_config.py path             # show which file is active
./scripts/dig_config.py show             # print effective config (defaults + file + env)
./scripts/dig_config.py get api.port     # one value
./scripts/dig_config.py set api.port 9000  # write one value
./scripts/dig_config.py export           # KEY=VALUE lines suitable for `eval` in a shell
```

### 1.3 Config file schema

A complete config with every supported key:

```json
{
  "version": 1,
  "api":  { "host": "127.0.0.1", "port": 8090 },
  "web":  { "host": "127.0.0.1", "port": 3000 },
  "dataDir": null,
  "logDir":  "/var/log/DIG",
  "log": {
    "maxBytes":     10485760,
    "backupCount":  5
  },
  "browserPreviewSampleRows": 100000
}
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `version` | integer | `1` | Schema version. Bumped on breaking changes (none yet). |
| `api.host` | string | `"127.0.0.1"` | Bind address for the FastAPI process. `0.0.0.0` exposes to LAN; pair with `DIG_AUTH_TOKEN`. |
| `api.port` | integer | `8090` | API port. |
| `web.host` | string | `"127.0.0.1"` | Bind address for the Next.js dev server. |
| `web.port` | integer | `3000` | Web UI port. |
| `dataDir` | string \| null | _(repo)_/`data` | Root of all user data — see [§3.4](#34-runtime-data-dir). `null` means "use the default location." |
| `logDir`  | string \| null | `/var/log/DIG` | Where rotated logs go. See [§4](#4-logs). `null` means "use the default" (the start script falls back to `~/Library/Logs/DIG/` on macOS or `~/.local/state/DIG/logs/` on Linux if it can't write to the default). |
| `log.maxBytes` | integer | `10485760` (10 MB) | Per-file rotation threshold. The rotator opens a new file (`dig-api.log` → `dig-api.log.1`) each time the active file crosses this size. |
| `log.backupCount` | integer | `5` | How many rotated files to keep. Older ones are pruned. |
| `browserPreviewSampleRows` | integer | `100000` | Cap on rows the in-browser DuckDB-WASM engine will load for live preview. Higher = slower preview, more accurate; lower = snappier. |

A `null` value in the file is treated as "no override" — the default wins.
That way old config files written before a key existed don't accidentally
zap the new default.

### 1.4 Environment-variable bridge

Every config key has a matching `DIG_*` env var. The start script calls
`dig_config.py export` and `eval`s the result, then individual env vars
override anything still ambiguous:

| Env var | Config path |
|---|---|
| `DIG_API_HOST` | `api.host` |
| `DIG_API_PORT` | `api.port` |
| `DIG_WEB_HOST` | `web.host` |
| `DIG_WEB_PORT` | `web.port` |
| `DIG_DATA_DIR` | `dataDir` |
| `DIG_LOG_DIR` | `logDir` |
| `DIG_LOG_MAX_BYTES` | `log.maxBytes` |
| `DIG_LOG_BACKUP_COUNT` | `log.backupCount` |

For everything that *only* exists as an env var (auth token, CORS allow-list,
resource limits, feature flags), see [`CONFIG.md`](CONFIG.md).

### 1.5 Sibling files in the config dir

Other things DIG keeps next to `config.json`:

```
~/.config/dig/
├── config.json     # the file documented above
├── auth.token      # auto-generated when --global, chmod 600
└── pid.json        # written by dig-start.sh, read by dig-stop.sh
```

`pid.json` is a runtime artifact (rebuilt on every start). `auth.token` is
the one with consequence — back it up if you depend on it for embedded
clients (those clients have the value baked in and don't tolerate rotation
without a redeploy).

---

## 2. Product tree

DIG runs as **two long-lived processes**, each launched through a
**rotating-log wrapper**, plus their children:

```
./scripts/dig-start.sh
    │
    ├── python3 dig_log_rotate.py --file …/dig-api.log -- dig-api  ← API wrapper (recorded in pid.json)
    │     └── dig-api  (uvicorn + FastAPI + DuckDB + SQLite + asyncio job manager)
    │           ├── runs Polars / DuckDB SQL for pipeline executions
    │           ├── serves REST + WebSocket on api.port
    │           └── spawns plugin / pack worker subprocesses on demand
    │
    └── python3 dig_log_rotate.py --file …/dig-web.log -- pnpm dev  ← Web wrapper (recorded in pid.json)
          └── pnpm dev → next dev  (Next.js 16 dev server, React 19, AG Grid, React Flow, DuckDB-WASM)
                └── on the client side: a browser tab loading DuckDB-WASM for in-tab preview
```

There is **no separate worker process**, no message broker, no separate
database server. Everything except the browser runs in one Python process
(API) and one Node process (web). The two never communicate directly —
the browser is always the intermediary, talking REST + WebSocket to the
API and HTTP to the web server.

The wrappers exist purely for log rotation and signal forwarding — they
have no business logic. `dig-stop.sh` kills the wrapper PIDs from
`pid.json`; the wrappers propagate the signal to their children, which
shut down cleanly.

For the deeper "what does each subsystem do" view (engine, registry,
storage, jobs, etc.), see [`ARCHITECTURE.md`](ARCHITECTURE.md). This page
is just the process graph.

---

## 3. Folder structure

There are **three** separate trees an operator should know about:

| Tree | Path | What lives there | Backup? |
|---|---|---|---|
| **Source repo** | _wherever you cloned DIG_ | Code, bundled steps, packs, scripts. | No (re-clone instead). |
| **User config** | `~/.config/dig/` | Settings, auth token, runtime PIDs. | **Yes** for `config.json` + `auth.token`. |
| **Runtime data** | `$DIG_DATA_DIR` (default `<repo>/data/`) | SQLite DB, uploaded datasets, pipeline outputs, caches. | **Yes** for everything except `cache/`. |
| **Logs** | `$DIG_LOG_DIR` (default `/var/log/DIG/`) | Rotated `dig-api.log` + `dig-web.log` and rotations. | Optional — pure history. |

### 3.1 Source repo layout

What you get from `git clone`:

```
<repo>/
├── README.md  CHANGELOG.md  LICENSE  SECURITY.md  THIRD_PARTY.md  TRADEMARK.md
├── start.sh  stop.sh  upgrade.sh  install.sh  restart_all.sh    # convenience wrappers around scripts/
├── Makefile
│
├── backend/                 # Python — FastAPI, DuckDB, SQLAlchemy, the engine
│   ├── pyproject.toml
│   ├── README.md
│   ├── connectors/          # built-in source connectors (CSV, Parquet, JSON, JDBC, …)
│   ├── steps/               # built-in transform steps (filter, group_by, export_to_map, …)
│   ├── tests/               # pytest suite
│   └── dig/                 # the actual Python package
│       ├── __init__.py  _settings.py
│       ├── ai/              # AI-feature wiring (chat, dispatcher, validators)
│       ├── api/             # FastAPI routers (datasets, pipelines, runs, settings, ws)
│       ├── cli/             # `dig-pack`, `dig-api`, etc. console_scripts entry points
│       ├── engine/          # DAG validator + executor + step base classes
│       ├── extensions/      # extension loader (pack data, pack plugins)
│       ├── jobs/            # asyncio job manager (run queue, progress, cancellation)
│       ├── observability/   # logging dict-config, tracing hooks
│       ├── plugins/         # plugin/pack discovery + loader
│       ├── protocols/       # ABCs the rest of the code talks to (Step, Connector, …)
│       └── storage/         # SQLAlchemy models + file-system helpers + Parquet writers
│
├── frontend/                # TypeScript — Next.js 16, React 19, Tailwind v4
│   ├── app/                 # App Router routes (pipelines, datasets, settings, …)
│   ├── components/          # Reusable UI (canvas, grid, dialogs, profile cards)
│   ├── lib/                 # Frontend-only helpers (api client, state, formatters)
│   ├── public/              # Static assets, including pinned duckdb-wasm bundles
│   ├── scripts/             # Build-time scripts (e.g. copy-duckdb-wasm)
│   └── tests/               # Playwright e2e + unit tests
│
├── shared/
│   └── schemas/             # JSON Schema 2020-12 — single source of truth for
│                            # pipeline.schema.json, step-manifest, connector-manifest
│                            # (Python + TypeScript both generate types from these)
│
├── plugins/                 # Drop-folder plugin tree — see §3.2
│   ├── connectors/          #   per-connector folders
│   ├── steps/               #   per-step folders
│   └── packs/               #   per-pack folders (each containing its own steps/)
│
├── Step-Pack-internal/      # The internal "source-of-truth" for first-party packs.
│                            # `dig-pack build` here, then copy data.zip + step files
│                            # into plugins/packs/<id>/. Operators never touch this dir.
│
├── samples/                 # CSV / JSON demo datasets the home-page button imports
├── data/                    # ⚠ Default DIG_DATA_DIR — covered in §3.4.
│                            # In production set DIG_DATA_DIR elsewhere.
│
├── docs/                    # Markdown docs (this file lives here)
├── scripts/                 # Operator scripts — see §3.3
├── internal/                # Internal-only scripts and notes (not shipped)
│
├── linux/  mac/             # OS-packaging scripts (.deb, .rpm, .app, .dmg builders)
└── licenses/                # Third-party license texts
```

A few things to know:

- **`backend/steps/` vs `plugins/steps/`** — the first ships in the repo and
  is what every install gets out of the box. The second is for steps you
  add locally (or distribute as pack tarballs). The runtime treats them
  identically.
- **`Step-Pack-internal/` is not consumed at runtime.** It's a build-time
  staging area. Only `plugins/packs/<id>/` is read by the loader.

### 3.2 Plugin tree

Plugins / packs / connectors all follow the same drop-folder convention:

```
plugins/
├── connectors/<id>/         # extra source connectors (one per dir)
│   ├── manifest.json        # connector metadata + param schema
│   └── connector.py         # implementation (subclass of dig.protocols.Connector)
│
├── steps/<id>/              # extra transform steps (one per dir)
│   ├── manifest.json        # step metadata, IO ports, param schema
│   └── step.py              # implementation (subclass of dig.engine.step.Step)
│
└── packs/<id>/              # bundled groups of steps + (optionally) data
    ├── pack.json            # pack metadata + step list + data resources
    ├── data.zip             # bundled reference data, lazily extracted
    │                        # (sha256-verified against pack.json)
    ├── _lookup_common.py    # any pack-internal helpers
    └── steps/<step_id>/     # one folder per step the pack contributes
        ├── manifest.json
        └── step.py
```

- The loader scans `plugins/` once at startup (and again when
  `Settings → Plugins → Reload` is clicked).
- The first-party packs that ship in the box (`geospatial_pack`,
  `business_charts`, `stats_pro`, `time_series_pro`, `dates_pack`,
  `statspack`) live here. You can disable individual packs from the
  Settings UI — that just deletes the folder.
- See [`PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md) for how to write your
  own; this page is about the layout an operator sees.

### 3.3 Operator scripts

Everything that controls a running DIG install:

```
scripts/
├── dig-bootstrap.sh        # one-time first-run setup (creates venv, installs deps, init config)
├── dig-install.sh          # idempotent dependency install (called by dig-start.sh on demand)
├── dig-start.sh            # ⭐ daily driver — boots both processes through log rotators
├── dig-stop.sh             # graceful shutdown via pid.json + port-orphan cleanup
├── dig-restart.sh          # convenience: stop + start
├── dig-restart-web.sh      # web-only restart (for frontend hot-edit during dev)
├── dig-status.sh           # is it running? what version? what ports?
├── dig-dev.sh              # foreground (no rotator) — used by `make dev`
│
├── dig_config.py           # config-file CRUD (init / show / get / set / export)
├── dig_log_rotate.py       # the log-rotator wrapper used by dig-start.sh
├── dig_startup_info.py     # writes the startup banner to logs (env, version, system info)
│
├── dig-run.sh              # one-shot: run a pipeline by ID and exit
└── dig-schedule.sh         # add a cron entry to run a pipeline on a schedule
```

`start.sh` / `stop.sh` / `restart_all.sh` / `upgrade.sh` at the repo root
are thin wrappers that just call into `scripts/dig-*.sh` — there for
discoverability ("the obvious thing should work").

### 3.4 Runtime data dir

The single most important directory for backups. Path: `$DIG_DATA_DIR`,
default `<repo>/data/` (override via env or `dig-config set dataDir
/path/to/data`).

```
$DIG_DATA_DIR/
├── .installed_version       # the DIG version that wrote into this dir
├── dig.sqlite               # primary DB — pipeline catalog, run history, settings, lineage
├── dig.sqlite-shm           # SQLite WAL shared-memory file
├── dig.sqlite-wal           # SQLite WAL log (live writes)
│
├── uploads/                 # input source-of-truth — files preserved forever
│   └── <ULID>-<original_filename>     # one file per upload
│   #   ⚠ DIG NEVER deletes anything in here. See "Input data is sacred" below.
│
├── inputs/                  # input source-of-truth (operator-managed) — files preserved forever
│   └── <whatever you put>             # files referenced via POST /datasets/from-uri
│   #   ⚠ Same rule: DIG NEVER deletes anything in here either.
│
├── datasets/                # 🤖 INTERNAL CACHE. Per-dataset canonical Parquet.
│   └── <ULID>.parquet                 # invisible to the end user; safe to wipe
│
├── outputs/                 # pipeline run outputs (one folder per run)
│   └── <RUN_ULID>/
│       ├── _intermediate/             # node outputs (kept for downstream nodes)
│       ├── <output_name>.parquet      # final outputs declared in the pipeline doc
│       ├── <node>.png / .html         # chart / map artifacts
│       └── ...
│
├── cache/                   # 🤖 INTERNAL CACHE — safe to delete; rebuilds on demand
│   ├── pack_data/<pack_id>/           # extracted pack data.zip contents
│   └── url-<hash>.<ext>               # HTTP-source connector response cache
│
├── tile_cache/              # 🤖 INTERNAL CACHE — OSM/Carto basemap tiles
│
└── extensions/              # extension state (currently empty in OSS)
```

#### Input data is sacred

DIG draws a hard line between **input data** (preserved forever) and
**caches** (DIG-managed, freely disposable). The contract:

| Kind | Where it lives | DIG can delete it? | Visible to user? |
|---|---|---|---|
| **Input data** | `uploads/`, `inputs/`, anywhere the user pointed `from-uri` | **Never** | Yes — referenced by name in the catalog |
| **Internal cache** | `datasets/<id>.parquet`, `cache/`, `tile_cache/` | Yes — freely | No — invisible implementation detail |
| **Run outputs** | `outputs/<run_id>/` | Yes (via run-history retention setting) | Yes — listed in the run-detail page |

The reasoning: the entire point of a data-preparation tool is to leave
the source untouched. A user who deletes a dataset reference from the
catalog should *never* discover their CSV is gone. If they want the
file gone, they delete it from the filesystem themselves — explicit,
deliberate, no DIG involvement.

Concretely, `DELETE /api/datasets/{id}` removes:
- the `datasets` table row (the **reference**)
- `data/datasets/<id>.parquet` (the **internal cache**)

…and never touches the file at the dataset's `source_uri`, regardless
of whether it lives in `uploads/`, `inputs/`, or anywhere else on the
filesystem. An audit-grade log line surfaces what was preserved:

```
INFO  dig.api.datasets: delete_dataset 01ABC: source file preserved at
      /Volumes/.../data/inputs/big.parquet (input data is never deleted by
      DIG; remove via filesystem if needed)
```

#### Backup boundaries

| Path | Strategy | Why |
|---|---|---|
| `dig.sqlite` (+ `-shm`, `-wal`) | `sqlite3 dig.sqlite ".backup ..."` while DIG is running, OR full file copy after `dig-stop.sh` | Live copy without `.backup` is unsafe — the WAL might not be checkpointed. |
| `uploads/`, `inputs/` | **Mirror** | Source-of-truth for raw user data; DIG can't recreate these. |
| `datasets/` | Skip | Internal cache — rebuildable from `uploads/` / `inputs/` by running ingest again. Mirror only if you want to skip re-ingest time on restore. |
| `outputs/` | Mirror or skip | Reproducible by re-running pipelines, but cheap to back up and saves CI time. |
| `cache/`, `tile_cache/` | **Skip** | Internal caches; rebuild themselves on demand. Pure waste in a backup. |
| `extensions/` | Mirror | Will hold extension state in future. |

#### Migration / move

Moving the data dir to a different disk:

```bash
./scripts/dig-stop.sh
mv /path/to/old/data /new/data
./scripts/dig_config.py set dataDir /new/data
./scripts/dig-start.sh
```

DIG records its installed version in `.installed_version`; `dig-start.sh`
warns (but doesn't refuse) if the binary is older than the data was last
touched by, so you don't accidentally run an old engine against a newer
on-disk schema.

---

## 4. Logs

### 4.1 Default location + per-platform fallback

Default: `/var/log/DIG/` (canonical Unix log path). On first start the
script bootstraps the dir with `sudo mkdir + sudo chown $(whoami)` so the
DIG process can write without elevated privileges thereafter.

If the sudo bootstrap fails (no sudo, declined password, non-interactive
shell), the start script falls back to a **per-user** location:

| OS | Fallback path |
|---|---|
| macOS | `~/Library/Logs/DIG/` (surfaces in **Console.app**) |
| Linux / BSD | `${XDG_STATE_HOME:-~/.local/state}/DIG/logs/` (XDG state base) |
| Windows | not officially supported — use WSL |

Override the path entirely:

```bash
./scripts/dig_config.py set logDir /var/log/DIG    # the default, made explicit
./scripts/dig_config.py set logDir /opt/dig/logs   # somewhere else
DIG_LOG_DIR=/tmp/dig-debug ./scripts/dig-start.sh  # one-shot
```

### 4.2 Files in the log dir

```
$DIG_LOG_DIR/
├── dig-api.log         # active (current) API log; appended in real time
├── dig-api.log.1       # most recent rotation
├── dig-api.log.2       # … older
├── dig-api.log.3
├── dig-api.log.4
├── dig-api.log.5       # oldest kept (rotated out next time)
├── dig-api.log.pid     # PID of the wrapped child (sidecar; auto-cleaned on stop)
│
├── dig-web.log         # same structure for the web (Next.js dev) process
├── dig-web.log.1
├── dig-web.log.2
…
└── dig-web.log.pid
```

Rotation is **size-based** (Python `RotatingFileHandler`). Defaults:
**10 MB per file × 5 files** per stream → 50 MB max per stream. Tune via
`log.maxBytes` / `log.backupCount` in the config or
`DIG_LOG_MAX_BYTES` / `DIG_LOG_BACKUP_COUNT` in the env.

### 4.3 Startup banner

Every start writes a self-contained banner to the **top of the active log
file** before the rotator takes over the live stream. Captures everything
worth attaching to a support ticket without asking a single question:

- timestamp, hostname
- DIG version + git SHA (with `-dirty` marker if uncommitted changes)
- OS / kernel / arch
- Python / Node / pnpm versions
- CPU count, total RAM
- data dir + free disk space there
- log dir
- the resolved effective config (defaults + file + env merged)
- every `DIG_*` and `NEXT_PUBLIC_DIG_*` env var (sensitive values masked
  by name — anything matching `TOKEN`, `SECRET`, `PASSWORD`, `KEY`,
  `PRIVATE` is shown as `head***tail (N chars)`)

The banner is generated by `scripts/dig_startup_info.py`; you can run it
standalone (`./scripts/dig_startup_info.py --also-stdout --target /dev/null`)
to dump the same info without restarting DIG — useful for support
tickets.

---

## 5. Common operator tasks

### Change the API or web port

```bash
./scripts/dig_config.py set api.port 9000
./scripts/dig_config.py set web.port 3001
./scripts/dig-restart.sh
```

### Bind to LAN (multi-device access)

```bash
./scripts/dig-restart.sh --global
./scripts/dig-restart.sh --global --save     # persist into config
```

The `--global` flag flips both `host` values to `0.0.0.0` for the current
run; `--save` writes the change into `config.json`. An auth token is
auto-generated and stored at `~/.config/dig/auth.token` (chmod 600). See
[`SECURITY.md`](../SECURITY.md) for the threat model.

### Move data to a different disk

```bash
./scripts/dig-stop.sh
rsync -aH /old/data/ /new/data/
./scripts/dig_config.py set dataDir /new/data
./scripts/dig-start.sh
```

### Tune log retention

```bash
./scripts/dig_config.py set log.maxBytes 52428800     # 50 MB per file
./scripts/dig_config.py set log.backupCount 10        # keep 10 generations
./scripts/dig-restart.sh
```

### Check what's running

```bash
./scripts/dig-status.sh                # ports + PIDs + version
cat ~/.config/dig/pid.json             # raw PID record
ps -ef | grep dig_log_rotate           # both wrappers + their children
```

### Rotate the auth token

```bash
./scripts/dig-stop.sh
shred -u ~/.config/dig/auth.token      # or rm on macOS (no `shred`)
./scripts/dig-start.sh --global        # auto-regenerates a fresh token
```

Any embedded clients with the old token in their config need to be
updated (this is intentional — token rotation is a security operation,
not a silent maintenance one).

### Upgrade

```bash
./scripts/dig-stop.sh
git pull
./upgrade.sh                           # pulls deps, runs migrations
./scripts/dig-start.sh
```

The `.installed_version` marker in the data dir gets updated automatically.
Migrations are forward-only; if you need to roll back, restore from
backup and run an older binary.

---

## 6. Cross-references

- [`CONFIG.md`](CONFIG.md) — every `DIG_*` environment variable in detail
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — how the components fit together internally
- [`SECURITY.md`](../SECURITY.md) — threat model + hardening guidance
- [`UPGRADING.md`](UPGRADING.md) — version-specific upgrade notes
- [`PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md) — how to extend DIG with custom packs
- [`SAVE_AND_VERSIONS.md`](SAVE_AND_VERSIONS.md) — pipeline history / undo / diff model

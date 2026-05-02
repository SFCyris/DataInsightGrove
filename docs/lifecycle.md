# Lifecycle — start, stop, status, config

DIG ships three cross-platform shell scripts (Linux + macOS) and an optional Mac `.app` wrapper. All four read the same JSON config so behavior is consistent across them.

## TL;DR

```bash
make setup        # one-time
make start        # detached, writes PID file, prints URLs
make status       # are services up? where?
make stop         # graceful TERM, escalates to KILL after 5s
make restart      # stop then start
make config-show  # print effective config (defaults + env + file)

# Custom ports, just for this run:
./scripts/dig-start.sh --api-port 9000 --web-port 4000

# Custom ports, persisted to ~/.config/dig/config.json:
./scripts/dig-start.sh --api-port 9000 --web-port 4000 --save
```

## The scripts

| Script | What it does |
|---|---|
| [`scripts/dig-start.sh`](../scripts/dig-start.sh) | Resolve config → start backend + web detached → wait until `/health` returns 200 and the web responds → write PIDs to `~/.config/dig/pid.json` → print URLs and exit. |
| [`scripts/dig-stop.sh`](../scripts/dig-stop.sh) | Read PID file, send SIGTERM, wait up to 5s, escalate to SIGKILL. Belt-and-braces: also `lsof -ti tcp:<port>` for any orphans on the configured ports. |
| [`scripts/dig-status.sh`](../scripts/dig-status.sh) | Hit `/health` and the web root; show ↑/↓ + actual ports from the PID file. Exit 0 if both up. |
| [`scripts/dig-dev.sh`](../scripts/dig-dev.sh) | Foreground mode for development — both services in one terminal with `[api]/[web]` log prefixes; Ctrl-C cleans up. Same as `make dev`. |
| [`scripts/dig_config.py`](../scripts/dig_config.py) | The config helper. `show`, `export`, `init`, `get`, `set`, `path`. |
| [`scripts/dig-run.sh`](../scripts/dig-run.sh) | Trigger one backend run of a pipeline (by id or name substring) and poll until done. |
| [`scripts/dig-schedule.sh`](../scripts/dig-schedule.sh) | `add` / `list` / `remove` recurring runs via the user's crontab. Each managed line is tagged `# DIG_SCHED:<pipeline>` so the script touches only its own entries. |

### Recurring runs (cron)

```bash
# every 15 minutes, run the "Revenue by country" pipeline
./scripts/dig-schedule.sh add "*/15 * * * *" "Revenue by country"

# nightly at 02:00, just a sample run
./scripts/dig-schedule.sh add "0 2 * * *"  "Cleanup customers" --sample 10000

./scripts/dig-schedule.sh list
./scripts/dig-schedule.sh remove "Cleanup customers"
```

The schedule fires `dig-run.sh` against the running backend — make sure DIG is started (or have your init system start it at boot).

### Linux .desktop launcher

```bash
./linux/install.sh    # one-shot, installs to ~/.local/share/applications/
```

After install, "DataInsightGrove" appears in your GNOME / KDE / XFCE application menu. Clicking it runs `dig-launch.sh` which starts the backend (no-op if already running) and opens the resolved web URL in your default browser via `xdg-open`.

## Flags accepted by `dig-start.sh`

| Flag | Default | Notes |
|---|---|---|
| `--api-port N` | `8090` | Backend port. Falls back to `DIG_API_PORT` env then config. |
| `--web-port N` | `3000` | Frontend port. |
| `--api-host H` | `127.0.0.1` | Bind address for the API (use `0.0.0.0` to expose on LAN). |
| `--web-host H` | `127.0.0.1` | Bind address for the web. |
| `--data-dir PATH` | `<repo>/data` | Where uploads / cached parquet / runs go. |
| `--foreground`, `-f` | (off) | Stay attached, prefixed logs, Ctrl-C cleans up. Same as `make dev`. |
| `--save` | (off) | Persist any of the above flags into the config file before starting. |

If a port is already in use, `dig-start.sh` exits 2 with a clear message rather than silently picking another port (Next.js's default behavior). Pass `--api-port` / `--web-port` to pick a free one.

## Configuration file

Path resolution (first that exists wins):

1. `$DIG_CONFIG` env var
2. `~/.config/dig/config.json` *(default; same on Linux + macOS)*
3. `<repo>/dig.config.json` *(dev fallback)*

Schema: [`shared/schemas/config.schema.json`](../shared/schemas/config.schema.json). Default contents:

```json
{
  "version": 1,
  "api":  { "host": "127.0.0.1", "port": 8090 },
  "web":  { "host": "127.0.0.1", "port": 3000 },
  "dataDir": null,
  "logDir": null,
  "browserPreviewSampleRows": 100000
}
```

`dataDir` and `logDir` accept `null` (use defaults: `<repo>/data` and the system tmp dir respectively). All other fields have sensible defaults if omitted.

### Config CLI examples

```bash
# write a default config file
./scripts/dig_config.py init

# show the effective config (after env + file overlays)
./scripts/dig_config.py show

# read one value
./scripts/dig_config.py get api.port

# write one value
./scripts/dig_config.py set api.port 9000
./scripts/dig_config.py set web.host 0.0.0.0
./scripts/dig_config.py set dataDir /var/lib/dig

# print the active config file path
./scripts/dig_config.py path
```

### Environment overrides

Recognized env vars (override config, overridden by CLI flags):

```
DIG_API_HOST   DIG_API_PORT
DIG_WEB_HOST   DIG_WEB_PORT
DIG_DATA_DIR
DIG_LOG_DIR
DIG_CONFIG     # path to a custom config file
```

## PID file

Written by `dig-start.sh` to `~/.config/dig/pid.json`:

```json
{
  "api": { "pid": 56992, "port": 9100, "log": "/tmp/dig-api.log" },
  "web": { "pid": 56993, "port": 4100, "log": "/tmp/dig-web.log" }
}
```

`dig-status.sh` prefers ports recorded here over the resolved config — that way it accurately reports a session that was started with `--api-port` flags even when those flags weren't `--save`d.

## The Mac app

`mac/DataInsightGrove.swift` is a tiny native AppKit + WKWebView wrapper. Build it once:

```bash
make mac-app
# or:
./mac/build.sh
```

The script:

1. Compiles `DataInsightGrove.swift` against AppKit + WebKit (~1s with `swiftc`).
2. Assembles a real `.app` bundle at `mac/build/DataInsightGrove.app/`.
3. Bakes the absolute repo path into `Info.plist` as `DIGRepoRoot` so the app can find the lifecycle scripts.
4. Ad-hoc codesigns it (so Gatekeeper allows the user to right-click → Open the first time).

Double-click the bundle (or `cp -R` it to `/Applications/`):

- Splash window: "🌳 Starting DataInsightGrove…" while the same `dig-start.sh` runs.
- Browser window: WKWebView pointing at whatever the resolved config says (default `http://127.0.0.1:3000`).
- Cmd-Q: runs `dig-stop.sh`. **Exception:** if the app detected DIG was *already* running before launch (start exited with code 2 = port busy), it doesn't stop anything on quit — assumes you want to keep your standalone session.

The Mac app **only** wraps the same shell scripts. No Mac-specific config, no Mac-specific data layout, no Mac-only features beyond the AppKit window itself. Linux users use the scripts directly and open `http://localhost:3000` in any browser.

## 🔐 Authentication + threat model

DIG defaults to a **single-user, loopback-only** posture: `127.0.0.1:8090` for the API and `127.0.0.1:3000` for the web UI. In that mode no authentication is required because nothing reaches DIG except your own browser.

If you want to expose DIG beyond loopback — running it on a remote dev box, a LAN-shared workstation, a VPN — you **must** set a bearer token first:

```bash
# Generate a strong random token (save this — you'll need it on the client too)
export DIG_AUTH_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')

# Bind to all interfaces (or a specific NIC)
export DIG_HOST=0.0.0.0
make start
```

The backend will refuse to start with a non-loopback `DIG_HOST` if `DIG_AUTH_TOKEN` is unset, with a clear error message — there's no way to accidentally expose a wide-open instance.

When the token is set, every API request must present:

```http
Authorization: Bearer <token>
```

WebSocket upgrades carry the token via `?token=...` because browsers can't reliably set custom headers on WS handshakes. The frontend reads `NEXT_PUBLIC_DIG_AUTH_TOKEN` and threads it through both transports.

`/health` and the static `/docs-files/*` are intentionally exempt — `/health` for liveness probes, docs because they're literal repo files anyway.

### What this defends against

- Anyone on the LAN browsing your IP and finding a wide-open data prep tool
- Cross-origin scripts: CORS is locked to the configured `DIG_CORS_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`)
- SQL-injection via predicate/expression params: `assert_safe_expr()` in [`backend/dig/engine/step.py`](../backend/dig/engine/step.py) denies `ATTACH`, `COPY`, file IO, and statement separators inside user-authored SQL fragments
- Path traversal via dataset URI: both `/runs/{id}/lineage` and `/runs/{id}/artifact` confine the resolved path under `data_dir()`

### What this does NOT defend against

- Multiple users sharing one token — DIG is single-user. The token is a shared secret, not per-user auth
- A compromised browser session
- Malicious plugin code (`plugins/steps/<id>/step.py` runs with full Python privileges by design)

For multi-user / production use, put DIG behind a proper reverse proxy (Caddy, nginx, Cloudflare Access) with its own auth layer.

## Cross-platform notes

- All scripts are POSIX-compatible bash — tested on bash 3.2 (macOS) and bash 5.x (Linux).
- No GNU-only flag use (`sed -i`, `find -printf`, etc.).
- `python3` does the JSON heavy-lifting so we avoid a `jq` dependency.
- Process management uses `setsid` if available, falling back to `nohup`.
- Port checks use `lsof -ti tcp:<port>` (present on both platforms).
- All paths use `~/.config/dig/` so a Linux user dropping the repo onto a fresh box gets the same config layout as macOS.

The Mac app is the only Darwin-specific artifact. Everything else runs unchanged on Linux.

# ⬆️ Upgrading DataInsightGrove

DIG ships with a small `upgrade.sh` helper at the repo root + an automatic
boot-time check that surfaces a notification on the first run after an
upgrade. Together they make "what version am I running, and is there a
newer one?" a one-command answer.

## TL;DR

```bash
./upgrade.sh --check          # is there a newer release on GitHub?
./upgrade.sh                  # interactive upgrade (prompts before applying)
./upgrade.sh --yes            # non-interactive upgrade (CI / scripted)
./upgrade.sh --to v1.0.2     # upgrade to a specific tag
```

After the script finishes, restart the backend. On boot, DIG records the
version transition and emits a `system.startup` notification with
`upgrade=true` and `prior_version=<old>` — visible in the Notifications
panel + matchable by any rule subscribed to `system.startup`.

## What `upgrade.sh` does

1. **Reads the current version** from `backend/pyproject.toml`.
2. **Asks GitHub** for the `releases/latest` tag of the repo (uses `gh`
   when available — bypasses the unauthenticated rate limit — falls
   back to a plain `curl`).
3. **Compares versions** via Python's `packaging.version`. Refuses to
   downgrade unless `--to` is explicit.
4. **Refuses to run on a dirty working tree.** Commit or stash before
   upgrading; the script will never force-overwrite local changes.
5. **Fetches tags + checks out the release.** Standard git operations,
   no rewriting of history.
6. **Reinstalls the backend** (`pip install -e ./backend`) if a venv is
   present at `backend/.venv/`.
7. **Installs frontend deps** (`pnpm install` or `npm install`) if
   `frontend/package.json` exists.
8. **Seeds `<DIG_DATA_DIR>/.installed_version`** with the OLD version
   (only when the marker doesn't already exist) so the next backend
   boot has something to compare against. The boot itself rewrites the
   marker to the new version after firing the transition event — the
   upgrade script never overwrites an existing marker.

If any step fails, the script aborts and prints the failing command +
context. Re-run after the underlying issue is resolved — every step is
idempotent.

## What the backend does on boot after an upgrade

The FastAPI lifespan hook calls `detect_and_record_version_transition`
([`backend/dig/storage/version_state.py`](../backend/dig/storage/version_state.py)):

- Reads `data/.installed_version`.
- Compares it to the running `dig.__version__`.
- If they differ:
  - Logs `version transition: <prior> -> <current>` at INFO.
  - Emits a `system.startup` notification event with
    `upgrade=true`, `prior_version=<prior>`, `version=<current>`,
    `level="notification"`.
  - Notification rules subscribed to `system.startup` or `system.*`
    pick it up. (Default rules don't — restart noise.)
- Rewrites the marker file to the current version.

Schema migrations are **separate** from the transition signal. The
additive-patches loop in `init_db()`
([`backend/dig/storage/db.py`](../backend/dig/storage/db.py)) runs on
every boot — not just on upgrades — and is idempotent. A column that
already exists is left alone; a column that's missing is added via
`ALTER TABLE ADD COLUMN`. Existing data is never touched, so downgrade
to an older minor that's missing a column is safe (the column stays in
the DB; the older code ignores it).

## What happens if the upgrade introduces a schema change?

For additive changes (new columns, new tables) — nothing manual. The
boot-time `init_db()` walks the additive-patches list and ALTERs in any
columns that aren't present yet.

For non-additive changes (column removed / renamed / retyped) — these
only happen at MAJOR version bumps. When a MAJOR ships with a
non-additive change, the upgrade flow surfaces an explicit prompt:

```
About to migrate the database from 0.x to 1.0. Back up data/dig.sqlite first.
Pass --allow-db-migration to confirm.
```

Re-run with `./upgrade.sh --allow-db-migration` after backing up. The
guard exists precisely so a routine `git pull` + restart never
silently makes your old data unreadable.

## CI / scripted upgrades

The script is designed to slot into a cron / CI hook:

```bash
# Nightly check + auto-upgrade on a staging host
./upgrade.sh --yes 2>&1 | tee /var/log/dig-upgrade.log
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | Up-to-date OR upgrade succeeded |
| 1 | Generic step failure (`set -euo pipefail` caught a non-zero exit from a git / pip / pnpm sub-command — see preceding stderr line for which command). |
| 2 | Bad arguments OR a required command (`git`, `curl`, `python3`) is missing on PATH. |
| 3 | Could not reach GitHub releases API (network down, rate-limited, behind a proxy). |
| 4 | Target version is older than current (would downgrade) |
| 5 | Working tree dirty — refuses to overwrite local changes |
| 6 | Target tag not found on remote |

Pin a known-good version in a corporate / disconnected environment:

```bash
./upgrade.sh --to v1.0.2 --yes
```

## Manual upgrade (without the script)

If you can't or don't want to use `upgrade.sh`:

```bash
git fetch --tags origin
git checkout v1.0.2          # or whichever tag
./backend/.venv/bin/pip install -e ./backend
( cd frontend && pnpm install )
printf '0.10.0\n' > "${DIG_DATA_DIR:-./data}/.installed_version"  # OLD version — the boot rewrites it after firing the transition event
```

Restart the backend. The boot-time hook will run.

## Backing up before an upgrade

DIG runs SQLite in WAL mode (the `dig.sqlite-wal` and `dig.sqlite-shm`
sidecars next to `dig.sqlite` are the write-ahead-log + shared-memory
files). A naive `cp dig.sqlite backup.sqlite` while the server is
running produces a corrupt copy that doesn't include the WAL — the
right way is `sqlite3 .backup`, which the server cooperates with:

```bash
mkdir -p ~/dig-backups
sqlite3 "${DIG_DATA_DIR:-./data}/dig.sqlite" \
  ".backup '$HOME/dig-backups/dig-$(date +%Y%m%d-%H%M%S).sqlite'"
```

The `.backup` command grabs a transactionally-consistent snapshot
even with the server still running. Restore is the reverse:
`cp backup.sqlite <data_dir>/dig.sqlite` (with the server STOPPED).

For paranoid upgrades, take a backup before running `./upgrade.sh`.
The script doesn't prompt for one — additive migrations (the only
kind allowed at MINOR) don't need one — but a MAJOR upgrade should.

## Rollback

```bash
git checkout v0.10.0
./backend/.venv/bin/pip install -e ./backend
( cd frontend && pnpm install )
printf '0.10.0\n' > "${DIG_DATA_DIR:-./data}/.installed_version"
```

DIG never destructively migrates data, so rolling back to a prior
minor is safe. The DB carries the extra columns the newer version
added; the older code ignores them.

Exception: **MAJOR-version rollbacks** may require a database restore
from backup if the MAJOR included a non-additive migration. The boot
notification fired by the original upgrade tells you whether such a
migration ran. DIG does not auto-snapshot the SQLite file, so before
running a MAJOR upgrade copy `data/dig.sqlite` somewhere safe — that
copy is your roll-back source if the migration turns out to be
incompatible.

## Where versions live

Single source of truth: `backend/pyproject.toml:version`. Everything
else reads from there:

- `dig.__version__` — `importlib.metadata.version("dig")` at import.
- `/health` — returns the same string in the response payload.
- Frontend — reads `/health.version`, never hardcoded.
- `data/.installed_version` — the last-booted marker file.
- `upgrade.sh` — parses `pyproject.toml` directly to print the current
  version + compare.

Changing the version means editing `pyproject.toml`. Everything else
follows automatically on the next boot.

## See also

- [`CHANGELOG.md`](../CHANGELOG.md) — what changed between releases
- [`docs/lifecycle.md`](lifecycle.md) — start/stop/status of the
  running DIG instance

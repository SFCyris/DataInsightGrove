# API stability + versioning policy

## 1.0-rc cycle (current)

DIG is at **1.0.0-rc2**. The architectural decisions described in
[Post-1.0 (the contract that will go live at GA)](#post-10-the-contract-that-goes-live-at-ga)
are LOCKED — schemas, protocol surface, extension architecture, IP
posture, and DB schema additivity. Round-2 / round-3 audit findings
are being landed in subsequent rc tags; nothing in the SemVer
contract below will change between rc1 and 1.0.0 GA without an
explicit `[BREAKING]` note in [`CHANGELOG.md`](../CHANGELOG.md).

For history: pre-1.0 (`0.x`) minor versions were allowed to break:

- HTTP API request / response shape
- Pipeline JSON schema (gated by `schemaVersion`; old documents continue to load if their version is still supported)
- Step manifest schema
- Pack manifest schema
- Database schema (migrated automatically by the additive-patches mechanism in `init_db`)
- Step parameter shapes inside a step's own version range

Patch versions (`0.10.0` → `0.10.1`) are bug-fix only — no breaking changes.

Every breaking change between minor versions appears in [`CHANGELOG.md`](../CHANGELOG.md) under a **Breaking** subsection.

## Post-1.0 (the contract that goes live at GA)

Starting at `1.0.0`, DIG follows [SemVer](https://semver.org):

- **MAJOR (1.x → 2.x):** breaking changes allowed in the HTTP API surface, pipeline schema (schemaVersion bumped), step manifest schema, and database schema. Migration tooling is provided.
- **MINOR (1.0 → 1.1):** additive changes only. New endpoints, new fields, new pipeline keys, new step types are introduced without breaking existing clients. The pipeline `schemaVersion` does NOT change.
- **PATCH (1.0.0 → 1.0.1):** bug fixes only.

### Additive-change rules

Clients must tolerate:

- New fields appearing in HTTP API responses. (JSON consumers should not error on unknown keys.)
- New keys appearing in `pipeline.metadata`, `pipeline.extensions`, `node.params`, `dataset.options`, `output.sink.options`. (These slots are explicitly `additionalProperties: true`.)
- New keys appearing under any `extensions` namespace. (Treat unknown namespaces as opaque pass-through.)
- New event kinds emitted by the notification system. (Rules that don't subscribe to them ignore them; rules that do see them via wildcard subscribe expectedly.)
- New step `category` values, new `engine.primary` values, new `webhook.on` values. (These were closed enums pre-1.0; they are free-form strings post-1.0. Unknown values render in the UI under a generic group / surface as an unrunnable engine / treat as "never fire".)

### Deprecation policy

A field / endpoint / parameter is **deprecated** when its replacement ships. We commit to:

- Document the deprecation in `CHANGELOG.md` and in the field's description.
- Keep the deprecated surface working for at least the **two minor versions after the one that deprecated it** before removal.
- Surface a runtime warning (HTTP response header `Deprecation: true` + `Sunset: <date>` per RFC 8594; backend logs) the first time a deprecated surface is hit per run.
- Provide a migration path in the changelog entry — what to use instead, and a one-liner if mechanical replacement is possible.

Removal of a deprecated surface always coincides with a MAJOR bump.

### Versioned endpoints

DIG today serves endpoints under the unversioned root (`/pipelines`, `/runs`, etc.). Starting with 1.0 we keep the unversioned routes as the "current" view. A second view, **`/v1/...`**, is introduced when we need to ship a breaking endpoint change without bumping MAJOR — same path under the version prefix freezes the 1.0 shape; the unversioned root migrates to the new shape.

Clients pinning long-term stability should use the versioned prefix. Interactive / quick-start usage should use the unversioned root.

### Header signal

Every API response carries `X-DIG-API-Version: 1.<minor>.<patch>` so clients can detect the server version programmatically without a separate `/health` call.

## Step versioning

Step types are versioned independently from the DIG release. A pipeline's `node.stepVersion` field pins a specific version (`semver` triplet). When a step's behaviour changes:

- **Behaviour-preserving fix** (`1.0.0` → `1.0.1`): pipelines pinned to `1.0.0` continue to use `1.0.0` until edited.
- **Additive change** (`1.0.x` → `1.1.0`): old pinned pipelines continue to use the old version; new pipelines pick up the new default.
- **Breaking change** (`1.x.y` → `2.0.0`): pipelines pinned to `1.x.y` continue to run unchanged. The step library shows a "newer version available" indicator. Users opt in by editing the node.

Step versions older than the current MAJOR's lowest supported step version are removed from the registry. Step manifests declare a `minDigVersion`; pipelines pinning a removed step surface a clear error rather than silently picking the next version up.

## Database schema

The SQLite schema is migrated automatically on startup via the additive-patches loop in `dig.storage.db.init_db`. No Alembic, no operator action.

When a future change is non-additive (column removal, type change, table rename), it ships as a one-time migration in a release labelled MAJOR, with:

- A pre-flight check that prints "About to migrate database; back up `data/dig.sqlite` first."
- An `--allow-db-migration` flag the operator must pass to proceed (CI / scripted upgrades pass it explicitly).
- A roll-forward-only design — no downgrade migrations.

## What we won't break, ever

These are commitments that survive even MAJOR bumps:

- `pipeline.id`, `node.id`, `dataset.id`, `pack.id`, `step.id`, `connector.id` continue to be stable string identifiers.
- The `schemaVersion` field continues to exist as the first sanity check on document load.
- The notification-event taxonomy stays additive — new kinds appear; old kinds keep meaning what they meant.
- `Run.id` is a stable ULID; `/runs/{id}` continues to work for runs from any prior version that hasn't been retention-pruned.
- The `.dig.json` pipeline export remains importable across MAJOR bumps via the migration tooling shipped with each MAJOR.

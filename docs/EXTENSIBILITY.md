# 🧩 Extensibility — forward-compat surfaces for plugin authors + forks

DIG's schemas reserve specific slots for **fields DIG core does not
interpret**. Vendors, enterprise builds, custom forks, and one-off
internal integrations use these slots to attach their own data
without colliding with future first-party fields and without forcing
a `schemaVersion` bump on every extension.

This page is the contract: which slots exist, who owns the keys
inside them, and how DIG handles values it doesn't recognise.

## The two patterns

### `metadata` — free-form, single namespace

Use for **pack-author or operator metadata** that isn't a vendor
extension: author name, internal pack-tracking ID, build timestamp,
the source URL the manifest was generated from, etc.

```jsonc
// step manifest.json
{
  "id": "my_step",
  "version": "1.0.0",
  "label": "🪄 My step",
  "category": "derive",
  "metadata": {
    "author_email": "team@example.com",
    "build_commit": "abc123def456",
    "internal_ticket": "DATA-4421"
  }
}
```

DIG never reads anything inside `metadata`. The frontend doesn't
display it. The API round-trips it untouched. It exists so you can
keep author / provenance info next to the manifest without polluting
the official fields.

### `extensions` — namespaced, multi-vendor

Use for **vendor / enterprise / fork-specific fields** that other
tools might also want to attach. Every key under `extensions` is a
**namespace identifier**; the value under it is opaque to anyone who
doesn't own the namespace.

```jsonc
// pipeline document
{
  "schemaVersion": 1,
  "id": "01ABC...",
  "name": "customer_overview",
  "extensions": {
    "acme": {
      "costCenter": "engineering-data",
      "complianceScope": ["SOC2", "HIPAA"]
    },
    "openlineage": {
      "facets": { "schema": { "_producer": "..." } }
    }
  }
}
```

Rules:

- **Namespace by your own short prefix.** Use the company / project
  name (`acme`, `bigco_data`, `openlineage`) — never `dig`, never
  `core`, never a name that looks like it could be official.
- **Anything inside a namespace is yours.** DIG core does not validate
  shape, type, or content inside `extensions.<your_namespace>`. You
  own the schema there.
- **Other tools should pass your namespace through untouched** when
  serialising / re-saving / exporting a pipeline. The official OSS
  reader does this by construction.
- **Don't depend on cross-namespace reads.** Your code reading
  `extensions.acme.x` is fine; reading `extensions.openlineage.y`
  while owning the `acme` namespace is a tight coupling that will
  break the day OpenLineage changes their shape.

## Where the slots are

Every persisted DIG document has these slots:

| Surface | `metadata` | `extensions` |
|---|---|---|
| **Pipeline document** (`pipeline.json`) | ✅ Top-level — common keys: `engineHints`, `annotations`, `variables` (used by [`docs/VARIABLES.md`](VARIABLES.md)) | ✅ Top-level |
| **Pipeline node** (`node.params`, `node.ui`) | `params` accepts arbitrary keys; `ui.note` is the free-text per-node annotation | (use top-level pipeline `extensions` keyed by node id if you must scope to a node) |
| **Dataset spec** (`datasetSpec.options`) | `options` accepts arbitrary keys, validated by the connector manifest's spec | (use connector-manifest `extensions` for connector-wide config) |
| **Output sink** (`outputSpec.sink.options`) | `options` accepts arbitrary keys | (use sink connector-manifest `extensions`) |
| **Step manifest** (`manifest.json`) | ✅ Top-level | ✅ Top-level |
| **Pack manifest** (`pack.json`) | ✅ Top-level | ✅ Top-level |
| **Connector manifest** (`manifest.json`) | ✅ Top-level | ✅ Top-level |

And, on the DB side:

| Model | `metadata` column | `extensions` column |
|---|---|---|
| `Dataset` | ✅ | ✅ |
| `Pipeline` | ✅ | ✅ |
| `Run` | ✅ | ✅ |

All are nullable JSON columns. Single-user OSS deployments leave them
NULL by default. Enterprise builds populate them via the
auth-context-aware ORM layer.

## Forward-compat enums (opened pre-1.0)

Several fields were closed enums in early DIG releases. They were
opened to **free-form strings with a documented set of known values**
before 1.0 to avoid the situation where introducing a new value (e.g.
a new compute engine) requires a `schemaVersion` bump.

### `step.engine.primary` — execution backend

Known values:

- `sql` — compiles to a DuckDB SQL fragment
- `polars` — Polars Python implementation
- `python` — generic Python implementation

A vendor or enterprise build may introduce new backends — `spark`,
`dask`, `snowflake_pushdown`, `bigquery_pushdown` — without changing
the schema. The OSS reader accepts the new value; if it has no
implementation registered for that engine, the step surfaces as
unrunnable with a clear error.

### `webhook.on` — pipeline-completion trigger

Known values:

- `always` — fires on both succeeded and failed
- `succeeded` — fires only on succeeded
- `failed` — fires only on failed
- `triggered` — never auto-fires (only manual via `webhook_trigger`)

Vendors may introduce new triggers (`partial_success`,
`data_quality_failed`, etc.). The OSS rule engine treats unknown
values as "never fire" — fail-safe by construction.

### `step.category` — step library grouping

Known values currently used in the shipped step library:
`shape`, `clean`, `derive`, `combine`, `aggregate`, `analyze`, `model`,
`validate`, `visualize`, `output`, `custom`. (`ingest` is reserved but
not yet used by any built-in step — connectors handle ingest today;
the category is available for future plugins.)

Packs may introduce new categories (e.g. `observability`,
`cost_optimization`). The frontend groups unknown categories under a
generic header.

## ID conventions

Identifiers (dataset ID, node ID, output ID) use
`^[a-z0-9][a-z0-9_:-]*$`. Lowercase alphanumerics, underscore,
hyphen, colon. The colon is reserved for **namespacing**:

```jsonc
{
  "datasets": [
    { "id": "org_42:customers", "connector": "postgres", "uri": "..." }
  ],
  "nodes": [
    { "id": "org_42:clean_emails", "step": "filter_rows", "stepVersion": "1.0.0", ... }
  ]
}
```

OSS users without a namespacing need can keep using plain snake_case
(`customers`, `clean_emails`) — same as before. The namespace prefix
is opt-in.

## How DIG handles values it doesn't recognise

| Surface | Unknown value |
|---|---|
| Key inside `extensions.<ns>` | Round-tripped untouched. Not validated. |
| Key inside `metadata` | Round-tripped untouched. Not validated. |
| `step.engine.primary` value with no registered implementation | Step is unrunnable; error message names the missing engine. |
| `webhook.on` value not in the known set | Webhook never fires (fail-safe). |
| `step.category` value not in the known set | Step appears under a generic group in the library UI. |
| New top-level field on a `pipeline.json` not yet known to the reader | Currently rejected because the schema is `additionalProperties: false`. Attach to `pipeline.extensions.<your_ns>` instead. |

## Examples

### Cost-center tagging at the org level

```jsonc
{
  "schemaVersion": 1,
  "id": "01PIPELINE_ULID",
  "name": "revenue_report",
  "metadata": {
    "variables": { "region": "us-east-1" }
  },
  "extensions": {
    "finance": {
      "costCenter": "data-platform",
      "budgetLineItem": "AWS-DATA-2026"
    }
  },
  "datasets": [...],
  "nodes": [...],
  "outputs": [...]
}
```

The pipeline serializes round-trips with the `finance` namespace
intact. A custom reporting tool reads `extensions.finance.costCenter`
to bill compute to the right team.

### Vendor pack with extra benchmark metadata

```jsonc
// pack.json
{
  "id": "acme_chart_pack",
  "version": "1.0.0",
  "label": "📊 Acme Charts",
  "description": "Premium chart steps maintained by Acme Inc.",
  "extensions": {
    "acme": {
      "premiumTier": "gold",
      "supportContact": "support@acme.com",
      "telemetryEndpoint": "https://acme.com/dig-pack-events"
    }
  }
}
```

DIG installs the pack normally — the `acme` namespace is opaque to
the loader. The pack's own runtime code can read its `acme.*` values
via `step.manifest["extensions"]["acme"]`.

### Enterprise audit hook on a Run

(Not user-authored — populated by an enterprise build's auth layer.)

```jsonc
// Run row exposed via /runs/{id}
{
  "id": "01RUN_ULID",
  "owner_id": "alice@corp.io",
  "org_id": "acme",
  "extensions": {
    "audit": {
      "approval_ticket": "JIRA-CHANGE-1234",
      "data_classification": "internal"
    }
  }
}
```

## See also

- [`docs/PIPELINE_FORMAT.md`](PIPELINE_FORMAT.md) — the full
  pipeline JSON shape, including the slot inventory
- [`docs/PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md) — short reference
  for adding step / connector plugins
- [`docs/AUTHORING_GUIDE.md`](AUTHORING_GUIDE.md) — deep guide for
  building production-grade extensions

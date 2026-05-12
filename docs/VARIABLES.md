# Variables in pipelines

DIG supports `{{ variable }}` substitution in three places:

1. **Dataset URIs** — `s3://bucket/{{ year }}/{{ month }}/{{ day }}/data.csv`
2. **Output sink URIs** — `file://exports/{{ pipeline_name }}/{{ today }}.parquet` (relative to the run's output directory; `file:///absolute` works too if the operator has set `DIG_EXPORT_ALLOW_ABSOLUTE=1`)
3. **Cell content**, via the `⏱ Add runtime column` step — `Report generated at {{ utime }} UTC`

Templates are rendered once per run, at the start of execution. Every node in the run sees the same timestamps + identifiers — a pipeline that uses `{{ year }}/{{ month }}/{{ day }}` will not straddle midnight even if the actual rendering happens microseconds apart.

The renderer is **not Jinja2** — it's a hand-written sandbox that supports only the substitution + filter syntax documented below. No conditionals, no loops, no attribute walking, no Python `eval`.

## Built-in variables

### Time and date (UTC)

| Variable | Value | Example |
| --- | --- | --- |
| `{{ today }}` | UTC date, ISO 8601 | `2026-05-11` |
| `{{ now }}` | UTC timestamp, ISO 8601 with `Z` | `2026-05-11T14:23:07Z` |
| `{{ year }}` | UTC year, 4-digit | `2026` |
| `{{ month }}` | UTC month, 2-digit | `05` |
| `{{ day }}` | UTC day-of-month, 2-digit | `11` |
| `{{ hour }}` | UTC hour, 2-digit | `14` |
| `{{ minute }}` | UTC minute, 2-digit | `23` |
| `{{ second }}` | UTC second, 2-digit | `07` |
| `{{ utime }}` | UTC time `HH:MM:SS` | `14:23:07` |
| `{{ epoch }}` | Unix seconds (UTC) | `1778415787` |

### Time and date (host-local)

| Variable | Value | Example |
| --- | --- | --- |
| `{{ today_local }}` | Host-local date | `2026-05-11` |
| `{{ now_local }}` | Host-local ISO with offset | `2026-05-11T07:23:07-07:00` |
| `{{ year_local }}` | Host-local year | `2026` |
| `{{ month_local }}` | Host-local month | `05` |
| `{{ day_local }}` | Host-local day | `11` |
| `{{ ltime }}` | Host-local time `HH:MM:SS` | `07:23:07` |

UTC and local are always separate variables. There is no ambiguous "current date" that depends on server timezone configuration.

### Run / pipeline context

| Variable | Value |
| --- | --- |
| `{{ run_id }}` | ULID of the current run |
| `{{ run_started_at }}` | UTC ISO timestamp of run start |
| `{{ pipeline_id }}` | ULID of the pipeline |
| `{{ pipeline_name }}` | Pipeline display name, slugified (lowercase, alphanumerics + `-`) |
| `{{ node_id }}` | DAG node ID. Empty in pipeline-level templates; populated inside per-step contexts (e.g. the `add_runtime_column` step). |
| `{{ user }}` | `"local"` in OSS; OIDC subject in Enterprise |
| `{{ env }}` | `"run"` (real run), `"preview"` (live-grid preview), `"dev"` |

### User-defined variables

Pipelines may declare variables under `pipeline.metadata.variables` (a free-form dict). Access via the `vars` namespace:

```jsonc
{
  "metadata": {
    "variables": {
      "region": "us-east-1",
      "bucket": "reports"
    }
  }
}
```

Then in a dataset URI: `s3://{{ vars.bucket }}/{{ year }}/data.csv` → `s3://reports/2026/data.csv`.

Only one level of dotted access is supported (`vars.region`, not `vars.config.region`). This blocks attribute-walking attacks like `{{ vars.__class__.__base__ }}`.

## Filters

Filters transform a variable's value. Chain with `|`.

| Filter | Effect | Example |
| --- | --- | --- |
| `upper` | ASCII uppercase | `{{ vars.region | upper }}` → `US-EAST-1` |
| `lower` | ASCII lowercase | `{{ pipeline_name | lower }}` |
| `strftime('<fmt>')` | Reformat a date/timestamp variable | `{{ today | strftime('%Y/%m/%d') }}` → `2026/05/11` |
| `replace('<old>', '<new>')` | Substring replace | `{{ utime | replace(':', '-') }}` → `14-23-07` |
| `default('<value>')` | Used when the variable is missing/empty | `{{ vars.region | default('us-east-1') }}` |
| `slug` | Filesystem-safe lowercase slug | `{{ pipeline_name | slug }}` |
| `safe` | Path-safety check (raises on traversal / forbidden chars) | `{{ vars.user_path | safe }}` |

## Path safety

When a rendered string lands in a filesystem path or URI (dataset URIs, sink URIs), the renderer enforces:

- **No cross-OS-forbidden characters** anywhere in the body: `<` `>` `:` `"` `|` `?` `*` and any ASCII control byte.
- **No `..` path traversal** segments.
- **No bare absolute paths** by default (URIs like `s3://...` and `file://...` are exempt; their host/path parts are still scanned for traversal and forbidden characters).

If your URI legitimately needs a `:` (e.g. inside a custom URI scheme not yet recognised), open an issue. The renderer prefers to refuse over to produce a path that fails on Windows.

## Cell-content templating

The `⏱ Add runtime column` step appends a column whose value is a rendered template. The template is evaluated once per run and every row in the output frame receives the same value.

Parameters:

- **New column name** — any valid column identifier.
- **Value template** — any `{{ }}`-substituted string (full variable surface + filters).
- **Type** — `string`, `integer`, `double`, `boolean`, `date`, `datetime`. The rendered string is coerced to this type.
- **Position** — `start` or `end`.

Examples:

| Template | Type | Resulting value |
| --- | --- | --- |
| `{{ today }}` | `date` | `2026-05-11` (date dtype) |
| `Report run at {{ utime }} UTC` | `string` | `Report run at 14:23:07 UTC` |
| `{{ today | strftime('%Y%m%d') }}` | `string` | `20260511` |
| `{{ vars.report_version | default('v1') }}` | `string` | `v1` |
| `{{ epoch }}` | `integer` | `1778415787` |

For per-row values (different value per row, derived from other columns), use the `derive_column` step instead — `add_runtime_column` is for the run-level constant case.

## Examples

### Dated output folder

Sink URI: `file://exports/{{ pipeline_name }}/{{ year }}/{{ month }}/{{ day }}/{{ utime | replace(':', '-') }}-orders.parquet`

Rendered (under the run's output dir): `file://exports/customer-overview/2026/05/11/14-23-07-orders.parquet`

> 📂 **Path tip**: prefer the two-slash `file://exports/...` form for relative paths under the run's output directory — that's always writable. The three-slash `file:///absolute/path/...` form only works when the operator has set `DIG_EXPORT_ALLOW_ABSOLUTE=1`. The bundled `📅 demo · variables` pipeline uses the relative form.

> 🔣 **Colon caveat**: `:` is a forbidden character inside filesystem paths and URI bodies (the path-safety check rejects it). Cell-content templates can use it freely (`Report run at {{ utime }}` renders to `Report run at 14:23:07`), but a URI template that includes `{{ utime }}` directly will fail validation. Use `{{ utime | replace(':', '-') }}` to turn `14:23:07` into a path-safe `14-23-07`.

### S3 with user variable + run ID disambiguation

Sink URI: `s3://{{ vars.bucket }}/{{ vars.region }}/{{ today }}/run-{{ run_id }}.parquet`

Rendered: `s3://reports/us-east-1/2026-05-11/run-01KS9B2F03ABCDEF.parquet`

### Report-time annotation column

Step: `⏱ Add runtime column`
- Name: `report_time`
- Template: `{{ now }}`
- Type: `datetime`

Every row in the output gets the same UTC ISO timestamp — useful for downstream consumers that want to know when a report was generated.

## Implementation notes

- Renderer: `backend/dig/engine/templates.py`
- Entry point for URIs: `dig.engine.templates.render_path` (with path-safety enforcement)
- Entry point for cell content: `dig.engine.templates.render_value`
- Executor hook: `_render_pipeline_paths` in `backend/dig/engine/executor.py` runs once at the start of `execute()`, before validation of the run's effective URIs by connectors.

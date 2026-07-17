# Plugin authoring — the short reference

If you've ever thought *"I wish DIG had a step that does X"* — this page shows you how to write one. Quick, no-fluff version: drop a folder, restart the backend, your step shows up in the library next to the built-in ones.

> 📘 **First time writing a DIG plugin?** Start with the [**deep authoring guide**](AUTHORING_GUIDE.md) instead — it builds a step *and* a connector from a blank folder and explains every line, with diagrams. This page is the short reference you come back to once you've shipped one or two.

## The shape

Every DIG transform — built-in or yours — follows the same two-file pattern: a `manifest.json` that describes it (so DIG can render a form for it in the UI) and a `step.py` (or `connector.py`) that does the work. Drop the folder somewhere DIG looks, and it shows up.

| If you want… | Drop the folder under | Used for |
|---|---|---|
| **Your own** step or connector | `plugins/steps/<id>/` or `plugins/connectors/<id>/` | Local extensions that survive `git pull` and don't touch DIG's source |
| A **built-in** | `backend/steps/<id>/` or `backend/connectors/<id>/` | Shipped with the repo (read these as reference) |

Both roots get scanned on backend startup. No `setup.py`, no `entry_points`, no manual registration — just the folder.

## Hello-world example

A complete worked example lives at [`plugins/steps/upper_string/`](../plugins/steps/upper_string/). It implements an "Uppercase string" step in two files:

```
plugins/steps/upper_string/
├── manifest.json     ← drives plugin registration + UI form generation
└── step.py           ← class UpperStringStep(Step) + `step = UpperStringStep(...)`
```

To verify it loaded:

```bash
curl -s http://127.0.0.1:8190/steps | jq '.[] | select(.id=="upper_string")'
```

To use it in a pipeline, add a node like:

```json
{
  "id": "n_upper",
  "step": "upper_string",
  "stepVersion": "1.0.0",
  "inputs": { "in": { "ref": "ds_customers" } },
  "outputs": ["out"],
  "params": { "column": "name" }
}
```

## File reference

### `manifest.json`

Authoritative schema: `shared/schemas/step-manifest.schema.json`. Required fields:

| Field | Notes |
|---|---|
| `id` | snake_case, unique. Used as `step` in pipeline nodes. |
| `version` | SemVer. Pipelines pin `stepVersion` for reproducibility. |
| `label` | Display name. Convention: leading category emoji (see `docs/UI_GUIDELINES.md`). |
| `description` | Surfaced as tooltip and step-library detail. |
| `category` | One of `ingest`, `shape`, `clean`, `derive`, `combine`, `aggregate`, `output`, `custom`. |
| `engine.primary` | `sql` (compiles to DuckDB), `polars`, or `python`. |
| `engine.browser` | `sql` (DuckDB-WASM runs the same SQL), `js`, or `none`. |
| `engine.deterministic` | True if same input + params → same output. Required for browser execution. |
| `io.inputs` / `io.outputs` | `{min, max, ports?}` — port names default to `["in"]` / `["out"]`. |
| `params` | Map of name → param spec (see below). Drives UI form generation. |
| `preview` | Hints: `rowImpact`, `schemaImpact`. Used for badges. |
| `tags` | Free-form, used in search. |

### `step.py`

Must:

1. Subclass `dig.engine.step.Step`.
2. Implement `to_sql(params, inputs) -> str` — return a SELECT statement that produces the step's output, given a map of port name → upstream CTE alias (already double-quoted).
3. Optionally override `infer_schema(input_schemas, params) -> dict[str, str]` — column name → logical type — so downstream steps' column pickers populate correctly. Default passes through the first input.
4. Export `step = MyStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))` at module top level.

The framework auto-validates the manifest on load. A bad manifest fails registration with a clear error in the API logs; the rest of the registry remains usable.

### Param types

`string`, `number`, `integer`, `boolean`, `enum`, `column_ref`, `column_refs`, `expression`, `regex`, `object`, `array`.

`column_ref` and `column_refs` are first-class — the UI form-generator queries the upstream node's inferred output schema (computed by `dig.engine.dag`) to populate the picker. Use `columnFrom` to point at a specific input port (defaults to `"in"`). Use `columnTypes` to filter by logical type, e.g. `["string"]`.

`visibleWhen: { otherParam: value }` makes the field conditional on another param's exact value. Equality only — keep it simple.

## Chart steps

Chart steps render an image artifact (PNG/SVG) instead of a tabular
output. They use `category: "visualize"`, `engine.primary: "polars"`,
`engine.browser: "none"`, and an `output_path` (or similar) param to
declare where the artifact lands. See
[`backend/steps/export_to_image/`](../backend/steps/export_to_image/)
for the canonical reference and the business-charts pack at
[`plugins/packs/business_charts/`](../plugins/packs/business_charts/)
for single-kind chart examples (funnel / pareto / waterfall).

### Inline preview is automatic

A chart step's image is rendered inline above the live grid the
moment a user focuses the node — no extra wiring needed. The
detection rule (in `frontend/app/pipelines/[id]/page.tsx`'s
`isChartFirstStep`) is **manifest-driven**:

- Any step with `category: "visualize"` and `engine.browser !== "sql"`
  is treated as chart-first.
- Plus `forecast` and `seasonal_decompose` (model-category steps
  that emit a chart preview as their headline output) — hardcoded
  exceptions; everything else flows from category.

Adding a new viz pack? Just declare the manifest fields above —
your chart step automatically gets the inline image preview, the
"▶ Run on backend" fallback when the upstream chain can't be
sampled in-memory, and the AI density warning (next).

### Density warning — `recommendedMaxRows`

Charts that depend on reasonable data density (scatter overplots
past ~5K, heatmap smears past ~50K, funnel stages should stay tens
not thousands) declare a soft upper bound on input rows in their
manifest. The editor renders a banner above the chart preview
**only when the upstream node's row count exceeds this value** —
suggesting [Continue] / [🎲 Sample] (the latter flips
`metadata.sampling` to `random` at the threshold size).

Two manifest shapes:

```jsonc
// Single-kind chart — one threshold for the whole step.
{
  "id": "funnel_chart",
  "category": "visualize",
  "engine": { "primary": "polars", "browser": "none" },
  "params": { /* … */ },
  "recommendedMaxRows": 30        // funnel stages should be tiny
}
```

```jsonc
// Multi-kind chart — per-kind map keyed by the `kind` param, with
// `_default` for kinds not explicitly listed.
{
  "id": "export_to_image",
  "category": "visualize",
  "engine": { "primary": "polars", "browser": "none" },
  "params": {
    "kind": { "type": "enum", "enumValues": ["scatter", "heatmap", "histogram", /* … */] },
    /* … */
  },
  "recommendedMaxRows": {
    "_default":  50000,
    "scatter":    5000,
    "scatter3d":  5000,
    "line":      10000,
    "heatmap":   50000,
    "hexbin":   200000,
    "histogram": 500000,
    "bar_counts": 50000
  }
}
```

The field is fully optional — chart steps without it just don't
get the banner. Authoring tip: pick thresholds based on visual
readability, not render time. The point is "past this point the
picture stops being a useful read" — render speed is a downstream
concern that often correlates but isn't the same thing.

The schema for the `recommendedMaxRows` field lives in
[`shared/schemas/step-manifest.schema.json`](../shared/schemas/step-manifest.schema.json)
(it accepts either an integer or the per-kind map) and the runtime
detection lives in
[`frontend/components/canvas/chart-density-warning.tsx`](../frontend/components/canvas/chart-density-warning.tsx).

## Connectors

Same pattern at `backend/connectors/<id>/` (or `plugins/connectors/<id>/`):

```
my_connector/
├── manifest.json     ← validated against shared/schemas/connector-manifest.schema.json
└── connector.py     ← class MyConnector(Connector) + `connector = MyConnector(...)`
```

`Connector` requires `read(uri, options) -> pl.LazyFrame` and optionally `write(frame, uri, options)`. The CSV connector at [`backend/connectors/csv/`](../backend/connectors/csv/) is a complete reference.

## Iteration tips

- **Rapid reload**: backend with `DIG_RELOAD=1 dig-api` (or `make backend-dev`) hot-reloads on file save.
- **Validate early**: hit `POST /pipelines/{id}/validate` to see schema-inference results without running.
- **Browser parity**: declare `engine.browser: "sql"` and your step gets free in-browser preview via DuckDB-WASM. The same `to_sql` output runs unchanged on both engines.
- **Tests**: drop a `tests.py` next to your `step.py`. Use `dig.engine.registry.steps().get("<id>").to_sql(...)` to assert SQL shape; run with `pytest backend/`.

## What plugins can't do

- Add new param types beyond the built-in set — the param schema is closed by design (the frontend's form generator only knows about the built-in types).
- Override the canvas node renderer — every node uses the same React Flow node component for visual consistency.
- Run network calls inside `to_sql`. Keep it pure — the SQL gets compiled into a CTE and may be executed in DuckDB-WASM as well.

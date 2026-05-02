# Plugin authoring

> 📘 **Looking for a step-by-step beginner walkthrough with diagrams?** Start with the [**deep authoring guide**](AUTHORING_GUIDE.md) — it builds a step and a connector from a blank folder, explaining every line. This page is the short reference you come back to once you know the shape.

DIG transforms are **plugins**. Drop a folder under `plugins/steps/<id>/` (user) or `backend/steps/<id>/` (built-in) and DIG auto-discovers it on backend startup. The same pattern applies to connectors at `plugins/connectors/<id>/` and `backend/connectors/<id>/`.

## Hello-world example

A complete worked example lives at [`plugins/steps/upper_string/`](../plugins/steps/upper_string/). It implements an "Uppercase string" step in two files:

```
plugins/steps/upper_string/
├── manifest.json     ← drives plugin registration + UI form generation
└── step.py           ← class UpperStringStep(Step) + `step = UpperStringStep(...)`
```

To verify it loaded:

```bash
curl -s http://127.0.0.1:8090/steps | jq '.[] | select(.id=="upper_string")'
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

# Pipeline format — what's inside a `.dig.json` file

Every pipeline you build in DIG can be saved as a single small JSON file and re-opened anywhere — on another machine, in a code review, in a Git diff, in another DIG installation. **This page is the friendly tour of what's actually in that file.**

You don't need to read it to *use* DIG; the editor builds and reads these files for you. But if you've ever wanted to:

- Tweak a pipeline by hand (rename twenty columns at once with sed, say)
- Generate pipelines programmatically from a template
- Diff two pipelines in code review
- Understand why DIG rejected an import

…this is the page that makes the inside of the file legible.

> **For the rule-perfect specification** that DIG's validator actually runs against — types, regex patterns, exact field names, default values — see [`shared/schemas/pipeline.schema.json`](../shared/schemas/pipeline.schema.json). It's a JSON Schema (2020-12) file. This page explains the *intent* of each piece in plain English; the schema is what your editor and the backend will both check against. If you ever spot the two disagreeing, please [open an issue](https://github.com/SFCyris/DataInsightGrove/issues) — they should match.

---

## File extension and shape

A pipeline is a plain JSON file with the extension `.dig.json`. No embedded scripts, no macros — just data. You can open one in any text editor, in `jq`, or paste it into ChatGPT.

The top level looks like this:

```json
{
  "schemaVersion": 1,
  "id": "01J…ULID",
  "name": "Customer cleanup",
  "createdAt": "2026-05-01T10:00:00Z",
  "updatedAt": "2026-05-01T10:30:00Z",
  "datasets": [ … ],
  "nodes":    [ … ],
  "outputs":  [ … ],
  "metadata": { … }
}
```

In one sentence: **a pipeline is a list of datasets you brought in, a list of steps you applied to them, and a list of outputs you want back out.**

---

## How nodes connect — the DAG, made implicit

In most "boxes-and-arrows" tools you have two lists in the file: a list of nodes and a separate list of arrows between them. DIG skips the arrow list. Each node names the upstream nodes it reads from, and *that* list of names is the arrow list.

Here's a join step that pulls from a filter step (called `n_filter_active`) on its left input port and from a raw dataset (`ds_orders`) on its right:

```json
{
  "id": "n_join_orders",
  "step": "join",
  "stepVersion": "1.0.0",
  "inputs": {
    "left":  { "ref": "n_filter_active", "port": "out" },
    "right": { "ref": "ds_orders" }
  },
  "outputs": ["out"],
  "params": { "on": [ { "left": "id", "right": "customer_id" } ], "how": "left" }
}
```

A `Reference` is just `{ ref, port? }`:
- `ref` — the id of an upstream node or a dataset (datasets have ids too, like `ds_orders` here)
- `port` — which named output of that upstream you want. Most steps only have one output (`out`) and you can leave `port` off.

**Why no separate `edges` array?** Two lists that have to stay in sync are an entire bug class. With one list (the references inside each node) the wiring is the references — they can't diverge.

---

## Dataset specs and the connector field

Each entry in `datasets` describes one source the pipeline reads from. A typical CSV-on-disk dataset looks like:

```json
{
  "id": "ds_main",
  "connector": "csv",
  "uri": "file:///…/data/datasets/01J…ULID.parquet",
  "options": { "delimiter": ",", "header": true },
  "label": "demo · customers"
}
```

`connector` and `uri` together tell the engine **what reader to use** and **where to read from**. The standard pattern: when DIG ingests a CSV (or XLSX, JDBC etc.) it caches a Parquet copy in `data/datasets/<ULID>.parquet`, then sets the pipeline-doc dataset's `uri` to that cached path. So a dataset originally ingested as CSV ends up pointing at a Parquet file on disk, with `connector` reflecting either the original ingest format or the cached format depending on when the doc was written.

### URI-extension wins over `connector` (self-healing)

The engine treats the **URI's file extension as the source of truth** when picking a reader, falling back to `connector` only when the URI is extension-less (JDBC, custom connectors, etc.). The helper is `effective_connector(spec)` in [`backend/dig/engine/pipeline.py`](../backend/dig/engine/pipeline.py):

- `*.parquet` → `read_parquet(...)`
- `*.csv` → `read_csv_auto(...)`
- `*.json` / `*.jsonl` / `*.ndjson` → `read_json_auto(...)`
- otherwise → `spec.connector` as written

This is **self-healing**: if a pipeline doc was saved with `connector: "csv"` before the dataset was re-cached as Parquet, the runtime still loads it correctly instead of crashing with a confusing `Error when sniffing file …parquet` from the CSV sniffer. Every reader-selection site in the engine routes through `effective_connector`:

- `compile_for_browser` (browser SQL)
- `executor._dataset_cte` (backend SQL)
- `dag._dataset_schema` (schema inference — must agree with the executor's reader, or column-validation lies)
- `compile_python._dataset_loader` ("Show as Python" Polars output)

This is Layer 4 of the AI-features defense ("Backend covers all paths") applied to dataset I/O — see [`AI_FEATURES.md`](AI_FEATURES.md). When you genuinely need to override extension-based detection (a `.csv.gz` that DuckDB should treat as compressed CSV, say), the right move is to surface that via `options` rather than try to fight the URI heuristic.

---

## Pipeline-level metadata

`metadata` is a free-form object on the document. DIG recognises a few well-known keys; everything else is preserved as-is so plugins and users can stash their own state without schema changes.

```json
{
  "metadata": {
    "trackLineage": true,           // enable per-row lineage on backend runs
    "sampling": {                   // editor preview sampling — see docs/SAMPLING.md
      "method": "random",           // "head" | "tail" | "random" | "systematic"
      "size": 100000,
      "seed": 42                    // optional, only meaningful for "random"
    },
    "publishedAsStep": {            // turn this pipeline into a reusable step
      "label": "My published step",
      "description": "What it does in one sentence",
      "emoji": "🪆",
      "category": "aggregate"
    }
  }
}
```

`publishedAsStep` is the marker that lifts a pipeline into the global step picker. Once set, the pipeline appears in every other pipeline's picker as `pipeline:<this-id>` with an emerald row tint, and `GET /steps/pipeline:<id>` returns its synthesised manifest. See [`SUB_PIPELINES.md`](SUB_PIPELINES.md) for the full lifecycle.

---

## Per-node UI hints

Each node has a `ui` block holding visual / authoring metadata that doesn't affect execution but travels with the document. Recognised fields:

```json
{
  "id": "n_filter",
  "step": "filter_rows",
  "stepVersion": "1.0.0",
  "inputs": { "in": { "ref": "ds_main" } },
  "outputs": ["out"],
  "params": { "predicate": "active = true" },
  "ui": {
    "x": 280,                       // canvas position (drag-to-arrange)
    "y": 100,
    "label": "Active customers",    // override of the manifest label
    "note": "Why this filter…",     // free-text note saved with the pipeline
    "exposedParams": {              // declare which params are tunable when published
      "predicate": {
        "alias": "filterExpr",
        "help": "Boolean filter expression"
      }
    }
  }
}
```

`exposedParams` ties into the sub-pipeline feature: when this pipeline is published (`metadata.publishedAsStep` set), each entry here surfaces as a customisable param on the synthesised step manifest. Consumers see them under their alias name; at compile time the inliner substitutes the consumer's value back into the inner node's `params[<paramKey>]`.

The 🪆 expose pill in the param-form's label row is the UI for editing this map — click once to expose, click again to remove. See [`SUB_PIPELINES.md#exposing-params`](SUB_PIPELINES.md#exposing-params).

---

## What happens when you save or run

Whenever the editor saves a pipeline, and again every time you click ▶ Run, the backend walks through five checks. They run fast and any failure surfaces in the UI before anything actually executes:

1. **Shape check.** Does the JSON match the schema? (Field names, types, required fields, value ranges.)
2. **Reference check.** Every `ref` points at something real — no dangling references.
3. **Cycle check.** The graph is a tree-of-steps, not a knot of mutually-referencing ones. (Topological sort; if it can't sort, you have a cycle.) **Sub-pipeline cycle check** runs in parallel: if your pipeline includes another pipeline as a step (`step: "pipeline:<id>"`) and that pipeline's transitive sub-pipeline graph closes back on you, the save returns 409 with a chain like `parent → dep → … → parent`. Same check repeats at run-start as a safety net.
4. **Sub-pipeline inlining.** Any node whose `step` is `pipeline:<id>` gets replaced with the spliced contents of the pinned source. This is invisible to the user — it just makes the rest of the pipeline see a flat DAG with namespaced inner-node ids. See [`SUB_PIPELINES.md`](SUB_PIPELINES.md) for details.
5. **Parameter check.** Each step's `params` block matches what *that step* expects (a filter has a `predicate`, a join has an `on`, etc.).
6. **Schema inference.** DIG walks left-to-right computing what columns each step produces. If your downstream step asks for a column that vanished upstream, you find out here, before any data moves.

If any check fails, the editor highlights what went wrong with a clear message. Nothing executes until the pipeline is structurally sound.

---

## See also

- [`docs/STEPS.md`](STEPS.md) — every step DIG ships with, plus what params it takes (auto-generated from the same schema, so it stays in sync).
- [`docs/AUTHORING_GUIDE.md`](AUTHORING_GUIDE.md) — how to add your own step or connector. The piece you'd plug into the `step` field above to introduce a new node type.
- [`shared/schemas/pipeline.schema.json`](../shared/schemas/pipeline.schema.json) — the JSON Schema this page describes in English. Use it for IDE autocomplete (`# yaml-language-server: $schema=…` works for JSON-with-comments too) or to validate generated pipelines in CI.

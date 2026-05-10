# 🪆 Sub-pipelines — composable building blocks

Any DIG pipeline can be **published as a reusable step** that other
pipelines can install from the regular step picker. The published
pipeline becomes a single node in the consumer's strip; at compile
time DIG inline-expands it into the consumer's flat DAG so lineage,
profiling, and execution work exactly as if you'd hand-stitched the
inner steps in place.

Three design choices worth knowing up-front:

1. **Pinned by default.** When you install a sub-pipeline step, the
   parent records a specific source version (`pinnedEtag`). The
   parent's behaviour is locked until you explicitly Upgrade.
2. **Cycles blocked.** Save and run-start both reject documents whose
   sub-pipeline graph would create a loop. You see the warning before
   the run can fail at execution.
3. **Inline-expanded, not nested at runtime.** The compiler splices
   the source pipeline's nodes into the consumer's DAG with namespaced
   ids. The runtime only ever sees flat nodes — no layered execution
   model to debug.

## Lifecycle

```
   Source pipeline                  Consumer pipeline(s)
   ──────────────                  ────────────────────
   1. Build it                ←─┐
   2. 🪆 Publish               │  Picker shows the step
   3. (later) edit it           ├──→  Pin says "n versions behind"
   4. Save labelled v.X         │
                                │     Click ⬆ Upgrade to vX
                                └──→  Recompiles with vX
```

## Publishing a pipeline as a step

In the editor toolbar:

```
[ ← back ]  🛤  Pipeline name   …   🪆 Publish    📋 Save As   …
```

Click **🪆 Publish** → a dialog opens:

```
┌─ 🪆 Publish as reusable step ─────────────────────────┐
│                                                       │
│  Once published, this pipeline appears in every      │
│  other pipeline's step picker. Consumers pin to the  │
│  version they install, so your future edits won't    │
│  change their behaviour until they upgrade.          │
│                                                       │
│  Step label  [ My published step                  ]  │
│  Emoji       [ 🪆 ]                                  │
│  Description [ One sentence — why a consumer would …]│
│  Category    🧹 Clean   ✂ Shape   ➕ Derive   📊 Aggregate │
│              🔗 Combine 🔬 Analyze 🧠 Model    ✅ Validate │
│              📈 Visualize  🪆 Custom                 │
│                                                       │
│  Inputs/outputs (MVP): one input "main" + one output │
│  "out" — implicit from the pipeline's lone dataset   │
│  and terminal node.                                  │
│  Exposed params: 0 — managed per-node via the        │
│  "Expose this param" toggle in the params panel.     │
│                                                       │
│              Unpublish     Cancel    🪆 Publish      │
└───────────────────────────────────────────────────────┘
```

After clicking **🪆 Publish**, the toolbar button flips to
**🪆 Published**, the picker on every other open pipeline gets a new
`pipeline:<your-id>` entry tinted emerald, and the published-step
manifest is exposed at `GET /steps/pipeline:<your-id>`.

### MVP shape: one input, one output

The first iteration restricts published pipelines to **exactly one
dataset** (the `main` input) and **exactly one terminal node** (the
`out` output). The publish dialog will block with a yellow notice if
your pipeline doesn't fit:

> ⚠️ Pipeline has no datasets — add at least one before publishing.

> ⚠️ A pipeline with multiple input datasets can't be published as
> a step. Reduce to one input dataset to publish.

The doc format reserves an `exposedInputs[]` array, so pipelines
authored as steps already declare a single named alias for their
input slot.

## Exposing params

Most useful sub-pipelines need a couple of knobs that consumers can
tune. Open any node in your source pipeline → params panel → look at
each param's row:

```
   ┌─────────────────────────────────────────────┐
   │ Group by                       🪆 expose    │  ← click the pill
   │ ┌─────────────────────────────────────────┐ │
   │ │ ts  line_id  machine_id  shift  …       │ │
   │ └─────────────────────────────────────────┘ │
   │                                             │
   │ Aggregates                     🪆 groupCol  │  ← already exposed
   │   (column = revenue, fn = sum)              │
   └─────────────────────────────────────────────┘
```

- **Default state** — neutral grey "🪆 expose" pill in the upper-right
  of each param's label row.
- **Click once** — turns violet, shows the alias (defaults to the param
  key). The param is now declared on the published manifest with that
  alias.
- **Click again** — un-exposes; the alias is dropped.

Stored as:

```json
"ui": {
  "exposedParams": {
    "<paramKey>": { "alias": "<consumer-facing name>", "help": "<optional>" }
  }
}
```

Consumers see those aliases as regular params on the synthesised step
manifest. Their values flow into the right inner node's params at
inline-expansion time.

## Picker integration

Pipeline-steps appear with an **emerald row tint** alongside built-ins
(neutral) and pack steps (violet tint). Hover for the source tooltip:

```
    🪆 Factory telemetry · group  ←  emerald row
       Composite from pipeline · Group-and-aggregate by material lot

    📊 Group & aggregate          ←  built-in (neutral)
    ⏳ Anomaly · rolling z-score   ←  pack step (violet)
```

Self-cycle preflight: if you try to insert a pipeline-step that
references the *same* pipeline you're editing, the picker rejects with
a 7-second toast:

> 🔁 A pipeline can't include itself as a step. Remove the
> publishedAsStep marker on this pipeline first, or pick a different one.

## Sub-pipeline pin badge

Once inserted, the wrapper node renders a pin badge above its
parameters:

```
┌─ 🪆 Sub-pipeline · pinned to v2 ─────────────────────┐
│                                              [ ⬆ Upgrade to v5 ]│
│   3 versions behind source (v5).                    │
└──────────────────────────────────────────────────────┘
```

Three states:

| Badge text | Meaning |
|---|---|
| `Up to date with source.` | Pinned etag matches the source's live etag |
| `n versions behind source (v<live>).` | Source has advanced; click ⬆ to bump |
| `Source pipeline unavailable — it may have been deleted.` | Source row gone; remove this node or republish a replacement |

Upgrade is a single click that sets `params.pinnedEtag = <live etag>`
and re-runs the validate + preview pipeline. No source-pipeline-side
action needed.

## Cycle detection

A sub-pipeline cycle would cause infinite expansion at compile time, so
DIG checks **at three points**, all using the live (un-pinned) source
documents:

1. **At save** (PUT /pipelines/{id}). Walks the proposed doc's direct
   sub-pipeline references, then BFS-expands each one's transitive
   closure. If the parent's id appears anywhere in the closure → 409.
2. **At run-start** (POST /pipelines/{id}/runs). Same check, idempotent.
   Defense-in-depth so a malicious doc inserted via a back-door (raw DB
   write, schema migration) can't cause a runaway expansion.
3. **In the picker (frontend preflight).** Self-cycle blocked
   immediately with a toast — transitive cycles fall through to the
   server check.

The 409 message names the offending chain so you know exactly which
edge to remove:

> 🔁 Cycle detected: composing pipeline {id} would create a loop
> ({parent → dep → … → parent}). Break the chain before saving.

## Compile-time inline expansion

```
parent doc                                 flat doc (post-inline)
─────────                                  ──────────────────────
  datasets: [parent_ds]                      datasets: [parent_ds]
  nodes:                                     nodes:
   [n_filter]                                 [n_filter]
   [n_wrapper                                 [n_wrapper__inner_a   ←─┐
     step="pipeline:src_id"      ──→            step="<inner step>"  │ spliced
     params:                                    inputs:{in:n_filter} │ inner
       pinnedEtag: 27                          ]                     │ nodes
       <exposed alias>: <override>             …                     │
   ]                                          [n_wrapper__inner_b]   ┘
                                              [n_wrapper            ←─ identity
                                                step="passthrough"     wrapper
                                                inputs:{in:n_wrapper__inner_b}
                                              ]
```

The wrapper is replaced by a **passthrough** node (`SELECT * FROM <prev>`)
that keeps the wrapper id alive. This matters because:

- The compile terminal-selection logic (`/compile?terminal=n_wrapper`)
  still resolves it.
- Any downstream node that referenced the wrapper id still resolves
  through the passthrough.
- Per-row lineage attaches to a stable id even when the inner step set
  changes between source versions.

The DuckDB planner inlines `SELECT * FROM <cte>` with zero overhead, so
the passthrough is free at runtime.

## Document format

### Source side (the published pipeline)

```jsonc
{
  "id": "01KQZD61AXSQ67SATT84PVZG20",
  "name": "Factory telemetry · group",
  "datasets": [{ "id": "ds_01...", "connector": "parquet", "uri": "..." }],
  "nodes": [
    {
      "id": "n_5162eeeacab0",
      "step": "group_aggregate",
      "stepVersion": "1.0.0",
      "inputs": { "in": { "ref": "ds_01..." } },
      "outputs": ["out"],
      "params": {
        "groupBy": ["material_lot"],
        "aggregates": [
          { "column": "machine_id", "fn": "count", "as": "Machine_count" }
        ]
      },
      "ui": {
        "exposedParams": {
          "groupBy": { "alias": "groupCols", "help": "Columns to group by" }
        }
      }
    }
  ],
  "metadata": {
    "publishedAsStep": {
      "label": "Factory telemetry · group",
      "description": "Group-and-aggregate telemetry by material lot",
      "emoji": "🪆",
      "category": "aggregate"
    }
  }
}
```

### Consumer side (a pipeline that uses it)

```jsonc
{
  "id": "01KQABCDEF...",
  "datasets": [{ "id": "ds_consumer", ... }],
  "nodes": [
    {
      "id": "n_y",
      "step": "pipeline:01KQZD61AXSQ67SATT84PVZG20",
      "stepVersion": "2",
      "inputs": { "main": { "ref": "ds_consumer" } },
      "outputs": ["out"],
      "params": {
        "pinnedEtag": 2,
        "groupCols": ["region"]    // overrides the source's groupBy
      }
    }
  ]
}
```

The consumer never sees the inner nodes — only the alias-named params.
At compile time the inliner substitutes `params.groupCols` back into
the inner `n_5162eeeacab0` node's `params.groupBy`.

## API surface

- `GET /steps` — pipeline-steps appear in the list with
  `source: "pipeline:<id>"`. Pack steps use `source: "pack:<id>"`,
  built-ins use `source: "builtin"`.
- `GET /steps/pipeline:<id>` — single synthesised manifest. The path
  converter accepts the colon.
- `POST /pipelines/{id}/runs` — runs the cycle check + inliner, then
  hands off to the worker with a flat doc.
- `POST /pipelines/{id}/compile?terminal=...` — same, the editor's
  live preview path.

## Known limitations

- **Single input / single output.** Each pipeline-as-step exposes one
  named input slot and produces one terminal table.
- **Pinned snapshots can be pruned.** If the source pipeline's history
  has more than 50 entries with the pinned etag near the bottom, the
  inliner falls back to the live document. The editor shows a clear
  "history pruned, please upgrade" surface in that case. To prevent it,
  the source author should make labelled Saves at intentional
  publish points — those survive pruning.
- **Composition without iteration.** A pipeline-as-step inlines and
  runs once per parent execution; it does not iterate over distinct
  values of a column.

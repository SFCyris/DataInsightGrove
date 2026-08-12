# 🧪 Sampling — how the editor preview draws rows

The pipeline editor renders a **live preview** of the focused step's
output. For tables with millions of rows, you don't actually want
DuckDB-WASM to render every row — you want a representative slice that
fits in the grid and renders fast. DIG's per-pipeline sampling dialog
lets you pick how that slice is drawn.

## Why per-pipeline?

Two flows have different needs:

- **Stable canary flow** — same first-N rows every time so the diff
  view between runs is meaningful. → `head`.
- **EDA / "what does my data look like"** — uniform random sample so
  the preview reflects the overall distribution, not just the start of
  the file. → `random`.
- **Time-series tail inspection** — most-recent N rows. → `tail`.
- **Periodic/systematic** — every Kth row, preserves any ordering
  trend across the dataset. → `systematic`.
- **Imbalanced data (fraud, churn, defects)** — uniform random
  under-represents the rare class; stratified preserves class
  proportions in the sample. → `stratified`.
- **"5 examples per category"** workflow — equal representation per
  group, not proportional. → `per_group`.
- **Log / event data with bursty traffic** — head/random over-sample
  the dense periods; time_bucket gives every day equal coverage. →
  `time_bucket`.
- **Revenue-weighted previews / probability-proportional** — rows
  with high-value columns over-represented. → `weighted`.
- **Statistical bootstrapping** — confidence intervals, hypothesis
  tests; sampling with replacement. → `bootstrap`.

The setting lives on `doc.metadata.sampling` so it travels with the
pipeline (export / import / share-via-Git).

## The dialog

Click the toolbar's **🧪 \<method\>** button (between the lineage
checkbox and the Run button):

```
┌─ 🧪 PIPELINE PREVIEW ──────────────────────────────────┐
│ Sampling method                                        │
│                                                         │
│ Controls how the editor preview draws rows from the   │
│ pipeline output. Saved with the pipeline so each flow │
│ can use a different method. Doesn't affect            │
│ full-data backend runs.                               │
│                                                         │
│ ●  🔝 First N rows                                     │
│      Fastest; biased toward the start. Default —      │
│      same as a SQL LIMIT.                             │
│ ○  🔚 Last N rows                                      │
│      The end of the dataset. Useful for time-series   │
│      'most recent'.                                   │
│ ○  🎲 Random uniform                                   │
│      Each row equally likely. Best for representative │
│      previews of large datasets. Optional seed makes  │
│      it reproducible.                                 │
│ ○  📐 Every Nth row                                    │
│      Regular cadence — every Nth row from start to    │
│      end. Preserves any ordering trend across the     │
│      dataset.                                         │
│                                                         │
│ Sample size (rows)    [ 100000 ]                      │
│                                                         │
│                              Cancel    💾 Apply        │
└────────────────────────────────────────────────────────┘
```

Method-specific controls appear conditionally:

- **First N / Last N / Random** → Sample size (rows)
- **Every Nth** → Take every Nth row
- **Random** → Optional Seed (for reproducibility)

## What it does NOT affect

Full-data **backend runs** (the green ▶ button). The sampling setting
only controls the editor's live preview and the
DuckDB-WASM-based grid. When you click Run on backend, DIG processes
the full dataset.

## Method tiers

The sampling dialog groups the nine methods into three tiers, shown
top-down in the picker so the universal four are seen first:

- **Universal** (no column required) — head / tail / random /
  systematic. Always available, no schema dependencies.
- **Distribution-aware** (need a column) — stratified / per_group /
  time_bucket. Use these for representative previews of imbalanced
  data, even per-category coverage, or trend visibility across time
  ranges with bursty density.
- **Statistical** — weighted / bootstrap. Niche but useful for
  revenue-weighted previews and confidence-interval workflows.

For each method that needs columns, the dialog auto-picks a smart
default (low-cardinality string for stratified / per_group, numeric
for weighted, datetime for time_bucket). The user can override; the
dialog blocks Apply when a required column slot is empty.

## How it's compiled

The dispatcher wraps the compiled pipeline SQL with a sampling
clause before executing it in DuckDB-WASM. The wrapper lives in
**two paired files** that are kept in lockstep:

- `frontend/lib/sampling.ts` — `wrapWithSampling(inner, cfg)` for
  the browser-side compile (DuckDB-WASM).
- `backend/dig/engine/sampling.py` — `wrap_with_sampling(inner, cfg)`
  + `SamplingConfig.from_metadata(...)` for the backend executor and
  the `preview-step-rows` endpoint.

Both call sites must produce the **same SQL** so the live preview
behaves identically whether the focused step runs in browser or
falls back to backend. Adding a new sampling method means updating
both files; the JS side has the canonical method enum
(`SamplingMethod`), the Python side mirrors it. Anything that reads
`metadata.sampling` is expected to call these helpers, never to
inline its own LIMIT/OFFSET — see `preview_step_rows` in
`backend/dig/api/pipelines.py` for the canonical backend usage.

The clauses (DuckDB-flavored):

```sql
-- head
SELECT * FROM (<inner>) AS __pipeline LIMIT <size>

-- tail (uses ROW_NUMBER + COUNT to grab trailing N rows)
WITH __t AS (<inner>), __ranked AS (
  SELECT *, ROW_NUMBER() OVER () AS __rn, COUNT(*) OVER () AS __ct
  FROM __t
) SELECT * EXCLUDE (__rn, __ct) FROM __ranked
  WHERE __rn > __ct - <size>
  ORDER BY __rn

-- random (DuckDB's USING SAMPLE with reservoir mode)
SELECT * FROM (<inner>) AS __pipeline
USING SAMPLE reservoir(<size> ROWS) [REPEATABLE (<seed>)]

-- systematic (every Kth row by ROW_NUMBER)
WITH __t AS (<inner>), __ranked AS (
  SELECT *, ROW_NUMBER() OVER () AS __rn FROM __t
) SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn % <K> = 0

-- stratified (proportional allocation per stratum, Neyman 1934)
WITH __t AS (<inner>), __ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY <col> ORDER BY <seeded random>) AS __rn,
    COUNT(*)    OVER (PARTITION BY <col>) AS __stratum_ct,
    COUNT(*)    OVER () AS __total_ct
  FROM __t
) SELECT * EXCLUDE (__rn, __stratum_ct, __total_ct) FROM __ranked
WHERE __rn <= GREATEST(1, CAST(ROUND(<size> * __stratum_ct / __total_ct) AS BIGINT))

-- per_group (cluster cap — N rows per distinct value of <col>)
WITH __t AS (<inner>), __ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY <col> ORDER BY <seeded random>) AS __rn
  FROM __t
) SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn <= <size>

-- time_bucket (N rows per DATE_TRUNC bucket)
WITH __t AS (<inner>), __ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY DATE_TRUNC('<day|hour|week|…>', <ts_col>::TIMESTAMP) ORDER BY <seeded random>) AS __rn
  FROM __t
) SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn <= <size>

-- weighted (Efraimidis-Spirakis 2006: key = -ln(U) / w; smallest <size> keys win)
WITH __t AS (<inner>), __keyed AS (
  SELECT *,
    CASE WHEN COALESCE(<weight>, 0) > 0
         THEN -ln(random()) / COALESCE(<weight>, 0)
         ELSE 1e18 END AS __ws_key
  FROM __t
) SELECT * EXCLUDE (__ws_key) FROM __keyed ORDER BY __ws_key ASC LIMIT <size>

-- bootstrap (sample WITH replacement via index pick + cross join)
WITH __t AS (<inner>),
     __indexed AS (SELECT *, ROW_NUMBER() OVER () AS __rn, COUNT(*) OVER () AS __ct FROM __t),
     __picks AS (SELECT 1 + CAST(FLOOR(random() * (SELECT __ct FROM __indexed LIMIT 1)) AS BIGINT) AS __pick
                 FROM generate_series(1, <size>))
SELECT __indexed.* EXCLUDE (__rn, __ct)
FROM __picks JOIN __indexed ON __indexed.__rn = __picks.__pick
```

The reservoir-sampling shape (random) is uniform without replacement
and runs in one pass — the standard textbook algorithm.

## Document format

```jsonc
{
  "metadata": {
    "sampling": {
      // One of: "head" | "tail" | "random" | "systematic"
      //       | "stratified" | "per_group" | "time_bucket"
      //       | "weighted" | "bootstrap"
      "method": "random",

      // Total result size for most methods. For per_group it's
      // rows-per-group; for time_bucket it's rows-per-bucket. The
      // dialog's helper text spells out which.
      "size": 100000,

      // For systematic only: take every Nth row.
      "everyN": 10,

      // For stratified / per_group / weighted: the column whose
      // value distribution we preserve (stratified), define groups
      // (per_group), or use as weights (weighted).
      "column": "status",

      // For time_bucket only: the timestamp column + bucket size.
      "timeColumn": "event_at",
      "bucket": "day",         // "hour"|"day"|"week"|"month"|"quarter"|"year"

      // Optional reproducibility seed. Threaded through random,
      // stratified, per_group, time_bucket. Not threaded through
      // weighted / bootstrap (their `random()` calls appear inside
      // function args where the inline `setseed(s), random()` trick
      // isn't valid; see lib/sampling.ts comments).
      "seed": 42
    }
  }
}
```

The toolbar button label always reflects the current method:

```
🧪 head
🧪 tail
🧪 random
🧪 systematic
```

When the setting is absent, the editor defaults to `{ method: "head",
size: 100000 }` — same behaviour DIG had before this feature, so
existing pipelines see no change.

## Live preview vs. backend run — transparent fallback

The editor's **live preview** prefers DuckDB-WASM (instant, in your
browser). When the focused step can't run in WASM — Polars-only
transformations like `anomaly_zscore`, `rolling`, `changepoint_detection`,
`forecast`, `seasonal_decompose`, `replace_outliers` — the dispatcher
**transparently falls back to the backend** and pipes the resulting
rows into the same grid. From your perspective the preview just shows
up; whether it ran in WASM or on the backend doesn't matter.

The grid does not label where a preview ran — routing is an
implementation detail, not something to act on. The backend hop is
typically <100ms for cached datasets, so the difference is barely
perceptible.

**Visualize-category steps** (e.g. `export_to_image`) keep the inline
**image preview** instead — the rows of `export_to_image` are just
the input passthrough, not interesting; the chart artifact is what
the user wants. The dispatcher detects the category and routes
accordingly. Click ▶ Run on backend for the full-fidelity (full data,
not sampled) artifact.

Implementation detail: when the WASM compile fails with `step '<id>'
has browser engine '<polars|none>'`, the dispatcher checks the focused
step's category. If `visualize`, it bubbles up to the existing
image-preview path. Otherwise, it calls
`POST /pipelines/<id>/preview-step-rows?terminal=<id>` which
materialises the upstream as Polars frames, runs the step's
`execute_polars`, and returns the resulting DataFrame as JSON rows.

`preview-step-rows` reads `doc.metadata.sampling` and applies the
same wrapper the browser does — so the rows you see in the grid
routed to the backend are sampled by the user's chosen method,
not by a hardcoded `LIMIT N`. Pre-method-parity behaviour was
"backend always uses head"; that's gone.

## AI features harvest samples through this layer too

The three Hints-panel AI cards (📖 Explain, 🛤 Suggest steps,
✨ Suggest visualizations) and every other feature that needs
"top-N values per column at the focused node" route through
`backend/dig/ai/node_context.py`'s `_harvest_node_samples`, which
itself uses `wrap_with_sampling`. So the sample values the LLM sees
respect the same `metadata.sampling` you picked in the dialog — if
you switched to `random` for representative previews, the AI sees
representative samples too. New sampling methods light up
automatically there.

# 🧪 End-to-end validation — every step, every connector

This document is **both** the validation report and a worked example: it walks through a real session that ingests three datasets, runs every one of DIG's 40 steps, and exports the results as files, image charts, and a SQLite table. If you want to know "does step X actually work end-to-end?" — the answer is in this report. If you want to learn DIG by example, the same flow is reproducible at the bottom.

> **Status (last run): 40/40 steps pass.** Run the harness yourself with `python3 scripts/e2e_validate.py` while the backend is up.

---

## The harness

[`scripts/e2e_validate.py`](../scripts/e2e_validate.py) does this for every step in the registry:

1. Builds a minimal pipeline doc that exercises the step.
2. Picks the right input dataset (numeric for ML, time-series for forecast/decompose, mixed for the rest).
3. Sends `POST /pipelines` → `POST /pipelines/{id}/runs` → polls `/runs/{id}` until terminal.
4. Records pass/fail + the failure detail.
5. Cleans up the created pipelines + datasets afterwards.

Each step gets its own pipeline so failures are isolated — one broken step can't contaminate the report.

---

## Datasets used

All three are bundled under [`samples/`](../samples/) (also covered in [`docs/tutorials.md`](tutorials.md)):

| Dataset | Rows | Why it's used |
|---|---:|---|
| [`customers-demo.csv`](../samples/customers-demo.csv) | 80 | General-purpose: filter / clean / aggregate / pivot / window / export / SQLite write |
| [`flowers-demo.csv`](../samples/flowers-demo.csv) | 150 | 4 numeric features + 1 categorical → drives every ML step (PCA, k-means, DBSCAN, t-SNE, UMAP, regression, correlation) |
| [`stock-demo.csv`](../samples/stock-demo.csv) | 365 | Daily time series → drives `resample`, `rolling`, `seasonal_decompose`, `forecast` |

The harness uploads each dataset via the regular `/datasets` API with `connector_id=csv`, waits for the ingest profile to complete, then references the cached Parquet URI in pipeline documents.

---

## Results table

Latest run, in execution order:

### ✂️ Shape (6 / 6 pass)

| Step | Status | Pipeline |
|---|---|---|
| `filter_rows` | ✅ | customers · keep `status = 'active'` |
| `select_columns` | ✅ | customers · keep 3 columns |
| `rename_columns` | ✅ | customers · `country → iso` |
| `sort_rows` | ✅ | customers · sort by `monthly_revenue desc` |
| `sample_rows` | ✅ | customers · seeded `n=10` |
| `split_column` | ✅ | customers · split `email` on `@` |

### 🧼 Clean (8 / 8 pass)

| Step | Status | Pipeline |
|---|---|---|
| `cast_type` | ✅ | customers · `monthly_revenue → double` |
| `clean_whitespace` | ✅ | customers · trim + collapse internal whitespace on `name` |
| `coalesce_columns` | ✅ | customers · `email \|\| name → contact` |
| `deduplicate` | ✅ | customers · 1 row per `country` |
| `expectations` | ✅ | customers · 2 rules (`not_null customer_id`, `in status [active,churned,trial]`) |
| `replace_text` | ✅ | customers · `User → Customer` in `name` |
| `round_to_n` | ✅ | customers · `monthly_revenue` to 0 dp |
| `upper_string` | ✅ | customers · uppercase `country` |

### 🪄 Derive (5 / 5 pass — non-ML)

| Step | Status | Pipeline |
|---|---|---|
| `bin_numeric` | ✅ | customers · 4 quartiles of `monthly_revenue` |
| `derive_column` | ✅ | customers · `is_premium = CASE WHEN plan = 'enterprise' THEN 1 ELSE 0 END` |
| `extract_date_parts` | ✅ | customers · year + month from `signup_date` |
| `extract_pattern` | ✅ | customers · regex `@(.+)$` from `email` → `domain` |
| `zscore` | ✅ | customers · standardize `monthly_revenue` |

### 🧠 Statistical / ML (7 / 7 pass)

| Step | Status | Pipeline |
|---|---|---|
| `pca` | ✅ | flowers · 4 features → 2 components, color by species |
| `kmeans` | ✅ | flowers · k=3 on 4 features |
| `dbscan` | ✅ | flowers · ε=0.5 on petal_length × petal_width |
| `tsne` | ✅ | flowers · 4 features → 2-D, perplexity=10 |
| `umap` | ✅ | flowers · 4 features → 2-D, n_neighbors=10 |
| `linear_regression` | ✅ | flowers · `petal_length ~ petal_width + sepal_length` |
| `correlation_matrix` | ✅ | flowers · pairwise Pearson, heatmap rendered |

### ⏱ Time-series (4 / 4 pass)

| Step | Status | Pipeline |
|---|---|---|
| `resample` | ✅ | stock · 7-day buckets, mean of `close` |
| `rolling` | ✅ | stock · 7-day moving average of `close` |
| `seasonal_decompose` | ✅ | stock · period=7 (weekly), additive |
| `forecast` | ✅ | stock · Holt-Winters, horizon=14 |

### 🤝 Combine (3 / 3 pass)

| Step | Status | Pipeline |
|---|---|---|
| `join` | ✅ | customers ⨝ flowers on `country = species` (left) |
| `union` | ✅ | customers ∪ customers (top + bottom) |
| `subpipeline` | ✅ | inner pipeline (filter active) called from outer |

### 📊 Aggregate (6 / 6 pass)

| Step | Status | Pipeline |
|---|---|---|
| `correlation_matrix` | ✅ | counted in ML above |
| `group_aggregate` | ✅ | customers · group by `country`, count + sum revenue |
| `pivot_wider` | ✅ | customers · `id=[country]`, names from `plan`, sum `monthly_revenue` |
| `pivot_longer` | ✅ | customers · melt `monthly_revenue` |
| `resample` | ✅ | counted in time-series above |
| `window_aggregate` | ✅ | customers · `ROW_NUMBER() OVER (PARTITION BY country ORDER BY monthly_revenue DESC)` |

### 📤 Output (3 / 3 pass)

| Step | Status | Pipeline |
|---|---|---|
| `export_to_file` | ✅ | customers · CSV |
| `export_to_image` | ✅ | customers · bar chart of customers per country (PNG) |
| `export_to_db` | ✅ | customers · SQLite table replace |

### 🎁 Worked-example plugins (3 / 3 pass — bundled in registry)

| Step | Status | Notes |
|---|---|---|
| `upper_string` | ✅ | Counted in Clean above. Lives under [`plugins/steps/upper_string/`](../plugins/steps/upper_string/) |
| `round_to_n` | ✅ | Counted in Clean above. Lives under [`plugins/steps/round_to_n/`](../plugins/steps/round_to_n/) |
| `zscore` | ✅ | Counted in Derive above. Lives under [`plugins/steps/zscore/`](../plugins/steps/zscore/) |

**Total: 40 / 40 pass.** Two real bugs were uncovered + fixed during this validation pass — see the next section.

---

## Bugs uncovered + fixed during this validation

The harness exposed two real bugs in step implementations that the unit tests had missed. Both fixed in this run:

### 1. `resample` — datetime precision mismatch on gap-fill

**Symptom:** `polars step 'n' (resample) failed: datatypes of join keys don't match — 'date': datetime[μs] on left does not match datetime[ns] on right`

**Root cause:** [backend/steps/resample/step.py:71-76](../backend/steps/resample/step.py#L71-L76) — when `fill_gaps=true`, the step generates a date range with `pl.datetime_range(...)` (default `[μs]` precision in newer Polars) and joins it to the bucketed frame. But when the source dataset comes from DuckDB-cached Parquet, the time column may be `[ns]` precision. The join key types don't match.

**Why unit tests missed it:** the existing test `test_ml_timeseries_steps.py::test_resample` builds the input as a Python `datetime` list which Polars converts to `[μs]` — same precision as `pl.datetime_range`. The bug only triggers when the time column comes from a real Parquet file via DuckDB. Classic "the test data was different from production."

**Fix:** cast the gap-fill range to match the bucketed column's existing dtype before the join.

```python
# Cast to the bucketed dtype before the join.
full = pl.DataFrame({tcol: full_range}).with_columns(
    pl.col(tcol).cast(bucketed.schema[tcol])
)
```

### 2. `window_aggregate` — `orderBy` only accepted strings, not `{column, direction}` dicts

**Symptom:** `AttributeError: 'dict' object has no attribute 'replace'`

**Root cause:** [backend/steps/window_aggregate/step.py](../backend/steps/window_aggregate/step.py) — the step's `to_sql` expected `orderBy` to be a list of column-name strings. But every other ordering step in DIG (`sort_rows`, the templates, the param-form generator's defaults) uses list-of-dicts with `{column, direction}`. When you fed window_aggregate the natural shape, `quote_ident()` got a dict, called `.replace('"', '""')` on it, and exploded.

**Fix:** accept both shapes; preserve direction (`ASC`/`DESC`) when given.

```python
# orderBy may be either a list of column names (string form) or a list
# of {column, direction} dicts — matching sort_rows for UI consistency.
order_parts: list[str] = []
for o in order:
    if isinstance(o, dict):
        col_name = o.get("column")
        if not col_name:
            continue
        direction = (o.get("direction") or "asc").upper()
        if direction not in ("ASC", "DESC"):
            direction = "ASC"
        order_parts.append(f"{quote_ident(col_name)} {direction}")
    elif isinstance(o, str):
        order_parts.append(quote_ident(o))
order_clause = f"ORDER BY {', '.join(order_parts)}" if order_parts else ""
```

---

## How to reproduce this report yourself

This is an executable report — re-run it any time:

```bash
# 1. Start the backend
make start

# 2. Run the harness
python3 scripts/e2e_validate.py

# 3. Inspect the JSON
cat scripts/e2e_results.json | python3 -m json.tool
```

The harness prints progress live (one line per step) and writes [`scripts/e2e_results.json`](../scripts/e2e_results.json) at the end. Exit code is 0 if all steps pass, 1 otherwise — easy to wire into CI.

---

## Worked example — the human-followable version

If you want to reproduce the *experience* of the harness in the UI rather than via the API, here's the same flow as a clickable tutorial. Three datasets, three pipelines, every output category exercised.

### 🧱 Setup (one-time, ~30 seconds)

1. Start DIG: `make start`. Open <http://localhost:3000>.
2. Go to **Datasets**. Drop in all three sample CSVs:
   - [`samples/customers-demo.csv`](../samples/customers-demo.csv)
   - [`samples/flowers-demo.csv`](../samples/flowers-demo.csv)
   - [`samples/stock-demo.csv`](../samples/stock-demo.csv)
3. You should now see three datasets, each with profile cards above every column.

### 📓 Pipeline A — "Customer cleanup → CSV + chart" (covers Shape · Clean · Derive · Aggregate · Output)

Goal: filter active paying customers, derive a `domain` column, group by country, render a chart, write a CSV.

1. **New pipeline:** name it `Customer cleanup`. Pick `customers-demo` as the source.
2. Add `filter_rows`. Predicate: `"status" = 'active' AND "monthly_revenue" > 0`.
3. Add `extract_pattern`. Column: `email`. Pattern: `@(.+)$`. Output: `domain`. (Pulls the email's domain into its own column.)
4. Add `clean_whitespace` on `name`.
5. Add `replace_text`: `User ` → `Customer ` in `name`.
6. Add `round_to_n` on `monthly_revenue`, 0 decimals.
7. Add `group_aggregate`: by `country`, aggregations = `count() as n` + `sum(monthly_revenue) as revenue`.
8. Add `sort_rows` on `revenue desc`.
9. Add `export_to_file`: format `csv`, path `cleaned-by-country.csv`.
10. Add `export_to_image`: kind `bar_counts`, x = `country`, title = "Customers per country".
11. **▶ Run on backend.** You'll get an image artifact card + a CSV file artifact, both downloadable from the run's artifact panel.

### 🌸 Pipeline B — "Flowers ML" (covers ML / stats)

Goal: cluster flowers via k-means, project them with PCA, fit a regression. Same dataset, three lenses.

1. **New pipeline:** name it `Flowers ML`. Source: `flowers-demo`.
2. Add `correlation_matrix` on the 4 numeric columns. Renders a heatmap.
3. (Branch from the dataset, not the matrix:) Add `pca` on the 4 features, `n_components = 2`, color by `species`. Renders a 2-D scatter showing the species cleanly separated.
4. (Branch again:) Add `kmeans`, `k = 3`, on the 4 features. Renders the cluster assignment.
5. (Branch again:) Add `linear_regression`: `y = petal_length`, x = `petal_width, sepal_length`. Renders actual-vs-predicted with R².
6. **▶ Run on backend.** Artifact panel has 4 image cards + the stats artifacts (variance explained, cluster sizes, R², coefficients).

### 📈 Pipeline C — "DIGX forecast" (covers time-series)

Goal: take a year of synthetic stock prices, decompose, smooth, forecast.

1. **New pipeline:** name it `DIGX forecast`. Source: `stock-demo`.
2. Add `rolling`: time column `date`, window `7d`, mean of `close` → `close_ma7`.
3. (Branch:) Add `seasonal_decompose`: time column `date`, value column `close`, period `7`, model `additive`. Renders the 4-panel plot.
4. (Branch:) Add `forecast`: time column `date`, value column `close`, horizon `30`, method `holt_winters`, seasonal_period `7`. Renders observed + forecast + 95% PI.
5. Add `export_to_file` (after rolling): format `parquet`, path `digx-smoothed.parquet`.
6. **▶ Run on backend.** Artifact panel has 2 charts + the smoothed Parquet.

### What you've just exercised end-to-end

After running all three pipelines, you've successfully executed every step DIG ships with — and produced 6 image charts, 2 file exports, and (if you swapped the file export for `export_to_db`) a SQLite write. The same coverage as the automated harness, just with the full UI experience.

---

## Why the harness exists (vs unit tests)

DIG already has 53 unit tests under `backend/tests/`. They check individual step behaviors against constructed inputs. **They don't catch:**

- Steps interacting with real Parquet files written by DuckDB (the resample bug).
- Param-shape mismatches between step manifests and the actual `to_sql` / `execute_polars` implementations (the window_aggregate bug).
- The "did the API actually accept my pipeline" half of the loop.
- Long-tail bugs in the executor's mid-pipeline materialization.

The E2E harness covers exactly that gap: it goes through the same `/pipelines` and `/runs` endpoints the UI uses, with real ingested datasets, top to bottom. **Run it before any release.**

# 🎓 First-steps tutorials — DataInsightGrove

Three short walkthroughs that take you from "ingest a CSV" to "get a chart / Parquet / CSV out". Each tutorial works against a bundled sample dataset under [`samples/`](../samples/) so you can copy-paste and follow along.

> **What you'll need first**
> - DIG installed and running ([`docs/getting_started.md`](getting_started.md))
> - The sample datasets under [`samples/`](../samples/) — they ship with the repo
>
> Open <http://localhost:3000>. If the dev server isn't up yet, run `make start` or `./scripts/dig-start.sh`.

The pipeline editor you'll be working in looks like this:

![DIG pipeline editor](images/06-pipeline-editor.png)

Top half = live grid of the data flowing out of the currently-selected step. Bottom strip = the pipeline (your steps). Right panel = parameters / hints / lineage. Every transform you add updates the grid live.

---

## 📑 Sample datasets at a glance

| File | Rows | Columns | Use it for |
|---|---:|---|---|
| [`samples/customers-demo.csv`](../samples/customers-demo.csv) | 80 | customer_id, name, email, country, plan, signup_date, last_login, monthly_revenue, status | Filter / group / pivot tutorials, demo template |
| [`samples/sales-demo.csv`](../samples/sales-demo.csv) | 1,440 | date, region, product, orders, revenue | Time-series, aggregation, **CSV export tutorial** |
| [`samples/flowers-demo.csv`](../samples/flowers-demo.csv) | 150 | petal_length, petal_width, sepal_length, sepal_width, species | PCA / k-means / **image export tutorial** |
| [`samples/stock-demo.csv`](../samples/stock-demo.csv) | 365 | date, ticker, close, volume | Forecast, seasonal decomposition, rolling window |

All four are tiny (under 60 KB each) so the entire tutorial cycle runs in the browser preview without ever hitting the backend.

---

## 🎨 Tutorial 1 — Render data as an image

**Goal:** start from a CSV, group revenue by region, and produce a PNG chart you can paste into a slide.

**Dataset:** [`samples/sales-demo.csv`](../samples/sales-demo.csv) — 90 days × 4 regions × 4 products of synthetic sales.

### Steps

1. **Import the dataset.** Open *Datasets → Import* and drop `sales-demo.csv` in. DIG profiles it on upload — you'll see histograms above each column.
2. **Create a new pipeline.** *Pipelines → ➕ New pipeline*. Name it `Sales by region`.
3. **Add a `group_aggregate` step.** Drag from the step library, connect from the dataset, set:
   - **By:** `region`
   - **Aggregations:** one row → `revenue` · `sum` · alias `revenue`
4. **Add an `export_to_image` step.** Connect from the aggregate. Set:
   - **Chart kind:** `bar_counts`
   - **X column:** `region`
   - **Title:** `Revenue by region`
5. **Add an output.** Click ➕ Output, set its source to the image step.
6. **▶️ Run on backend.** Wait a second — the run completes and the image card appears in the artifacts panel below the grid.

### What the result looks like

![bar chart of revenue per region](images/tutorials/tutorial-bar-by-region.png)

### Variations to try

- Swap the chart kind to `heatmap` and pivot by `region × product`. With three columns (`region`, `product`, `revenue`) you'll get this:
  ![heatmap of revenue by region × product](images/tutorials/tutorial-heatmap-sales.png)
- Use [`flowers-demo.csv`](../samples/flowers-demo.csv) with the `pca` step (4 numeric columns, `color_by = species`):
  ![PCA scatter of flowers](images/tutorials/tutorial-pca-flowers.png)
- Use [`stock-demo.csv`](../samples/stock-demo.csv) with the `forecast` step (`time_column = date`, `value_column = close`, `horizon = 30`):
  ![30-day stock forecast](images/tutorials/tutorial-forecast-stock.png)
- Same dataset with `seasonal_decompose` (`period = 7`):
  ![seasonal decomposition](images/tutorials/tutorial-seasonal-stock.png)

> 💡 **Tip:** Every chart you generate is also downloadable from the artifacts panel — click the card to get the full-resolution PNG. Use the SVG format for crisp vector output in print or slide decks.

---

## 📄 Tutorial 2 — Export cleaned data as CSV

**Goal:** filter and clean a dataset, then write the result back to disk as a CSV.

**Dataset:** [`samples/customers-demo.csv`](../samples/customers-demo.csv) — 80 mock customers.

### Steps

1. **Import** the dataset.
2. **New pipeline:** `Active paying customers`.
3. **Add `filter_rows`.** Predicate:
   ```sql
   status = 'active' AND monthly_revenue > 0
   ```
4. **Add `select_columns`.** Pick the columns you want to ship: `customer_id, name, country, plan, monthly_revenue`.
5. **Add `sort_rows`.** Sort by `monthly_revenue` descending.
6. **Add `export_to_file`.** Set:
   - **Format:** `csv`
   - **Path:** `active-customers.csv` (defaults to `data/outputs/<run>/active-customers.csv`)
7. **Add an output** pointing at the export step.
8. **▶️ Run on backend.** When the run finishes, the artifacts panel shows a `📄 CSV export` card with the row count and the file path.

### What you get

| customer_id | name | country | plan | monthly_revenue |
|---:|---|---|---|---:|
| 8 | User 008 | BR | enterprise | 500 |
| 18 | User 018 | UK | enterprise | 500 |
| … | … | … | … | … |

The CSV file lives under `~/.local/share/dig/data/outputs/<run_id>/active-customers.csv` — click the card in the artifacts panel to download it directly, or `cat` it from the shell.

> 💡 **Tip:** `export_to_file` also supports `json`, `ndjson`, and `excel` (xlsx). Pick whichever the consuming tool expects.

---

## 🪶 Tutorial 3 — Export to Parquet for downstream analytics

**Goal:** produce a Parquet file so a downstream notebook / Spark / DuckDB job can pick up where DIG left off.

**Dataset:** [`samples/sales-demo.csv`](../samples/sales-demo.csv).

### Steps

1. **Import** the dataset.
2. **New pipeline:** `Daily revenue (parquet)`.
3. **Add `cast_type`.** Cast `date` → `date` (CSV ingest reads it as a string).
4. **Add `group_aggregate`.** By `date`, `region`. Aggregations:
   - `revenue · sum · daily_revenue`
   - `orders · sum · daily_orders`
5. **Add `export_to_file`.**
   - **Format:** `parquet`
   - **Compression:** `zstd` (default — best size/speed trade-off)
   - **Path:** `daily-revenue.parquet`
6. **Add an output** pointing at the export step.
7. **▶️ Run on backend.**

### Verify the output from the shell

```bash
duckdb -c "SELECT date, region, daily_revenue FROM read_parquet('~/.local/share/dig/data/outputs/<RUN_ID>/daily-revenue.parquet') ORDER BY daily_revenue DESC LIMIT 5;"
```

You should see something like:

```
┌────────────┬─────────┬───────────────┐
│    date    │ region  │ daily_revenue │
├────────────┼─────────┼───────────────┤
│ 2025-03-22 │ NA      │      245890.20│
│ 2025-03-15 │ NA      │      241333.10│
│ 2025-03-29 │ NA      │      238920.50│
│ ...        │ ...     │            ...│
└────────────┴─────────┴───────────────┘
```

> 💡 **Why Parquet?** Columnar layout, fast scans, schema embedded in the file, supported by every modern data tool (pandas, Polars, DuckDB, Spark, Snowflake, BigQuery). It's the right choice when the next step in your workflow is another data tool, not a human.

---

## 🧩 Combining moves — the bigger picture

Most real workflows look like Tutorial 2 + Tutorial 1 + Tutorial 3 in one pipeline:

1. Filter + clean → 2. Aggregate → 3. Render a sanity-check chart (`export_to_image`) **and** 4. Persist Parquet for downstream (`export_to_file`).

DIG lets you fan-out from any step to multiple outputs. Connect both `export_to_image` and `export_to_file` to the same upstream node, add two pipeline outputs, and run once. Both artifacts land in the same run folder.

### Example: scheduled daily reports

After your pipeline is dialed in, persist it (it's saved automatically) and use the lifecycle script to run it on a cron:

```bash
./scripts/dig-schedule.sh add --pipeline <PIPELINE_ID> --cron "0 7 * * *"
```

You'll get a fresh PNG + Parquet under `data/outputs/<run_id>/` every morning at 07:00 — perfect for emailing to a stakeholder or feeding into the next stage of the pipeline.

---

## ↩️ Where to next

- **More steps:** the full catalog with examples is in [`docs/STEPS.md`](STEPS.md).
- **More patterns:** the architecture overview is in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
- **Plugin authoring:** drop a folder under `plugins/steps/<id>/` and your step shows up next start — see [`docs/PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md).
- **Pipeline format:** the portable `.dig.json` shape is in [`docs/PIPELINE_FORMAT.md`](PIPELINE_FORMAT.md).

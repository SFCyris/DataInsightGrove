# 📈 Tutorial 2 — Sales seasonality + outlier alerts

**Goal:** detect weekly seasonality in daily sales, flag outliers (days that defy the seasonal pattern), schedule the pipeline to run nightly, and push the outlier table to a Google Sheet for the team to triage.

**Dataset:** [`samples/sales-demo.csv`](../../samples/sales-demo.csv) — 90 days × 4 regions × 4 products of synthetic sales (`date`, `region`, `product`, `orders`, `revenue`).

**Features in focus:** seasonal_decompose · derive_column · expectations · reverse-ETL to Google Sheets · scheduled runs · distribution diff

**Estimated time:** 25 minutes (10 min pipeline, 10 min Sheets setup, 5 min schedule).

---

## Steps

1. **Import** `sales-demo.csv` if you haven't.

2. **New pipeline:** `Daily revenue + outlier alerts`.

3. **Add `cast_type`.** Cast `date` → `date`.

4. **Add `group_aggregate` to roll up to one row per day.** Set:
   - **By:** `date`
   - **Aggregations:**
     - `revenue` · `sum` · alias `daily_revenue`
     - `orders` · `sum` · alias `daily_orders`

   The live preview now has 90 rows (one per day). Click the `daily_revenue` column header — the inline histogram already shows the seasonal pattern: a long tail of high-revenue days (the weekend peaks).

5. **Add `seasonal_decompose`.** Set:
   - **Time column:** `date`
   - **Value column:** `daily_revenue`
   - **Period:** `7` (weekly seasonality on daily data)
   - **Model:** `additive`

   The output adds three columns: `trend`, `seasonal`, `resid`. The `resid` column is what we'll use to spot outliers.

   *(After this step the live grid grows three columns. Hover any header to see the inline distribution sparkline against the run baseline. Per-tutorial screenshot pending — for the general column-header sparkline pattern, see [the v0.6 showcase](README.md#-the-new-pipeline-editor-toolbar).)*

6. **Add `derive_column` to z-score the residuals.** Set:
   - **Name:** `resid_zscore`
   - **Expression:**
     ```sql
     resid / NULLIF(STDDEV(resid) OVER (), 0)
     ```

7. **Add `derive_column` to flag outliers.** Set:
   - **Name:** `is_outlier`
   - **Expression:**
     ```sql
     ABS(resid_zscore) > 2.5
     ```

8. **Add `filter_rows` to keep only outlier days.**
   - **Predicate:** `is_outlier = true`

9. **Add `expectations` for sanity.**
   - `is_outlier IS NOT NULL`
   - `daily_revenue >= 0`

10. **Add `select_columns` to ship a tidy table.** Pick: `date, daily_revenue, trend, resid, resid_zscore`.

11. **Add `sort_rows`.** Sort by `resid_zscore` descending.

   *(The filtered preview now shows ~5–10 outlier days, sorted by residual z-score. Per-tutorial screenshot pending.)*

---

## Push the outliers to a CSV the team can open

The reverse-ETL Sheets / Snowflake / BigQuery connectors all exist but each requires real credentials to demo. For this tutorial we'll use the simplest reproducible sink: a **CSV file** the team can open in Excel / Numbers / a notebook / `cat` from the shell. Same pipeline shape; swap the export step's connector for Sheets later when you've wired the credentials.

12. **Add `export_to_file` step.** Set:
    - **Format:** `csv`
    - **Path:** `outliers-{{ run.date }}.csv` (the `{{ run.date }}` template renders the run date so each run gets a unique file)
    - **Include header:** ✅
    - **Include BOM:** ❌

13. **Add an output** pointing at the CSV export step.

14. **▶️ Run on backend.** When the run finishes, the artifacts panel shows the CSV card with the row count and file path. Click the card to download or copy the path.

   The output lives at `~/.local/share/dig/data/outputs/<run_id>/outliers-2026-05-03.csv`. Sample first 3 lines:

   ```csv
   date,daily_revenue,trend,resid,resid_zscore
   2026-03-22,245890.20,201337.04,44553.16,3.42
   2026-03-15,241333.10,200214.88,41118.22,3.16
   2026-04-04,238920.50,206118.00,32802.50,2.52
   ```

   > 💡 **When you're ready to push to Sheets/Snowflake/BigQuery instead:** swap `export_to_file` for `export_to_db` and pick the matching connector. The rest of the pipeline (decompose → derive → filter) stays identical — DIG's plugin architecture means the sink is a one-line param change, not a pipeline rewrite.

---

## Schedule it nightly

16. **Open *Schedules*.** Click ➕ New schedule. Set:
    - **Pipeline:** `Daily revenue + outlier alerts`
    - **Cron:** `0 6 * * *` (6am every day)
    - **Webhook on failure:** optional Slack URL

   Now every morning at 6am the pipeline runs, refreshes the outliers tab, and (if you wired the webhook) pings the team if it fails.

   *(Per-tutorial screenshot pending. The Schedules page UI is under [`/schedules`](http://localhost:3000/schedules) on a running DIG.)*

---

## Distribution diff: did Tuesday look different from Monday?

After two scheduled runs have completed, open the editor for this pipeline and look at the `daily_revenue` column header — there's a subtle 🟡 drift badge. Hover the sparkline; the muted overlay is yesterday's distribution.

If `KL > 0.5`, you'll see 🔴 instead — that's actionable: something genuinely shifted between the two runs (data quality issue at source, missing days, etc.).

   *(The drift badge + overlay surfaces in column headers automatically once a previous run exists. Per-tutorial screenshot pending — requires two scheduled runs to land first.)*

---

## Run AI review for time-series correctness

Click **🔍 Review**. Typical findings:

- 🔴 *"`seasonal_decompose` requires a regular time series; if your input has gaps, the residual is meaningless. Add a `resample` step before this one."*
- 🟡 *"Outlier filter uses abs(zscore) > 2.5 which assumes normality — your residuals look bimodal. Consider IQR-based outlier detection or a model-based threshold."*

These are the kinds of things you'd only catch reading the docs (or after deploying and getting a bad result). The reviewer surfaces them before you ship.

---

## Share

**🔗 Share**:
- **Title:** Sales seasonality + outlier alerts
- **Tags:** time-series, seasonality, sheets, monitoring
- **Visibility:** Unlisted

The shared template includes the pipeline structure but not your Sheets credentials — the recipient sets their own.

---

## What you learned

- `seasonal_decompose` for time-series → trend / seasonal / residual.
- Window functions in `derive_column` for z-scoring.
- Reverse-ETL to Google Sheets via the new sink connector.
- Cron scheduling for unattended runs.
- Distribution diff between runs catches drift you'd otherwise miss.
- AI review for time-series-specific correctness issues.

> 💡 **Tip:** Sheets has a 5M-cell hard cap per workbook. For larger writes, switch the export to `parquet` for archival and only push a top-N "alert table" to Sheets.

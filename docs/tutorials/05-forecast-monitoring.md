# 📊 Tutorial 5 — Stock forecast + drift monitoring (Engineer mode)

**Goal:** forecast 30 days of stock prices, schedule the pipeline daily, and use the distribution-diff overlay + AI review to monitor for prediction drift between consecutive runs. This tutorial uses Engineer-mode features (Live SQL toggle, raw lineage graph, full review verbosity) — switch via `⌘⇧E` or *Settings → 🌱 Expertise mode*.

**Dataset:** [`samples/stock-demo.csv`](../../samples/stock-demo.csv) — 365 days of one synthetic ticker (`date`, `ticker`, `close`, `volume`).

**Features in focus:** forecast · scheduled runs · distribution diff · Live SQL toggle · AI review (Engineer verbosity)

**Estimated time:** 25 minutes.

---

## Prerequisite: switch to Engineer mode

Press `⌘⇧E` until the bottom-right pill in the command palette reads **🌳 Engineer**. You'll see a new toolbar button: **{ } SQL**. The AI review panel now shows confidence percentages on each finding. The lineage drawer defaults to graph view.

   ![Pipeline editor in Engineer mode — note the `{ } SQL` button on the right of the toolbar](../images/tutorials/advanced/10-template-editor-rich.png)

---

## Build the pipeline

1. **Import** `stock-demo.csv`.

2. **New pipeline:** `Stock 30-day forecast`.

3. **Add `cast_type`** to convert `date` → date. (Live SQL view shows the cast as a `CAST("date" AS DATE)` in the CTE — open it now to get familiar with the SQL ↔ visual mapping.)

4. **Add `filter_rows`.** Predicate:
   ```sql
   ticker = 'DIGX'
   ```
   (the bundled demo only has the `DIGX` synthetic ticker; if you bring your own multi-ticker file, this is the place to pick which one to forecast)

5. **Add `sort_rows`.** Sort by `date` ascending.

6. **Add `forecast` step.** Set:
   - **Time column:** `date`
   - **Value column:** `close`
   - **Horizon:** `30`
   - **Confidence intervals:** ✅ on

   The output adds `forecast`, `lower_bound`, `upper_bound` columns. Click each header — you can immediately see the uncertainty grow over the forecast horizon (lower/upper diverge).

   *(Three new columns join the grid: `forecast`, `lower_bound`, `upper_bound`. Hover any header for the inline distribution sparkline; the bounds will visibly diverge over the horizon.)*

7. **Add `derive_column` to flag wide-uncertainty days.**
   - **Name:** `is_uncertain`
   - **Expression:**
     ```sql
     (upper_bound - lower_bound) > (forecast * 0.4)
     ```

8. **Add `expectations`.**
   - `forecast IS NOT NULL OR date <= (SELECT MAX(date) FROM input)` (forecasts only for future dates)
   - `lower_bound <= forecast AND forecast <= upper_bound` (interval sanity)

9. **Add `export_to_image`.**
   - Chart kind: `line`
   - X column: `date`
   - Y columns: `close, forecast, lower_bound, upper_bound`
   - Title: `30-day forecast with 95% CI`

10. **Add an output** pointing at the image step.

11. **▶️ Run on backend.** The chart appears.

   *(Per-tutorial chart screenshot pending. The bundled forecast result from the existing first-steps tutorial gives you the same kind of view:)*

   ![Forecast result chart from the first-steps tutorial — same shape applies](../images/tutorials/tutorial-forecast-stock.png)

---

## Open the Live SQL view

Click **{ } SQL** in the toolbar. The bottom drawer slides up showing the compiled DuckDB query — every CTE annotated with its node ID + label. Try clicking around: the SQL view is read-only (Tier 1), but copying the query and pasting it into a DuckDB CLI gives you the exact query DIG runs.

   ![Live SQL view — keyword-tinted CTE chain with each node ID annotated](../images/tutorials/advanced/10-live-sql-rich.png)

> 💡 The Live SQL view's terminal defaults to your currently-focused step. Click a different step in the strip and re-open SQL — you'll see the query compiled up to that point only.

---

## Schedule it daily, watch for drift

12. **Open *Schedules* → ➕ New schedule.** Cron `0 18 * * 1-5` (6pm weekdays). Wire the pipeline.

13. **Wait for at least 2 runs to land** (or trigger manual runs back-to-back if you want to see this immediately).

14. **Re-open the editor.** Look at the `forecast` column header. The sparkline now has a **muted overlay** — that's the previous run's distribution. If the model drifted significantly, you'll see a 🔴 drift badge.

15. **Hover the sparkline.** The popover shows current vs previous distribution + a KL divergence number. Engineer mode shows the raw KL value.

   *(Per-tutorial screenshot pending — requires two scheduled runs to land first. The drift badge + muted overlay appear automatically once a previous-run profile snapshot exists.)*

16. **For deeper investigation, open the per-column "compare to" picker.** It lets you compare to any historical run (Engineer mode shows up to 50 of them). Picking last week's same-day run is the canonical "is today's prediction normal vs last Wednesday?" question.

---

## Run AI review (Engineer mode verbosity)

Click **🔍 Review**. Engineer mode shows confidence percentages and SQL-level diffs. Typical findings:

- 🔴 *"Forecast variance grows linearly with horizon — at horizon=30 the upper/lower spread is 40% of the predicted value, which is the threshold your `is_uncertain` derive flags. Consider a shorter horizon or expressing forecasts as ranges, not point estimates."* (95% confidence)
- 🟡 *"`SELECT MAX(date) FROM input` in the expectation will scan the input each time; for large datasets, materialize it as a CTE and reuse."* (78% confidence)
- 🔵 *"No anomaly check on `volume` — historical volume spikes correlate with price-prediction misses."* (54% confidence — below the engineer-mode hide threshold but visible)

Apply the second one — DIG opens the diff drawer with the proposed mutation. Accept and the pipeline updates. The AI never silently changes anything; you always see the diff first.

---

## Share

**🔗 Share**:
- **Title:** Stock 30-day forecast with drift monitoring
- **Tags:** time-series, forecast, monitoring, engineer
- **Visibility:** Public

The shared template includes the schedule definition (recipients can adapt the cron), the expectations, and the AI-review history (so the recipient can see what's been suggested + dismissed previously).

---

## What you learned

- **Engineer mode** unlocks Live SQL, full lineage graphs, raw-confidence AI review.
- `forecast` step + 30-day horizon + confidence intervals.
- Multi-line plots with Y-column lists in `export_to_image`.
- **Live SQL view** as the round-trip artifact between visual + raw SQL crowds.
- **Distribution diff** between scheduled runs catches model drift you'd miss by eye.
- **AI review** in engineer mode surfaces structural concerns + SQL-level optimizations.

> 💡 **Tip:** The drift badge thresholds are configurable in `~/.config/dig/config.json` — set `drift_warn_kl=0.05` for higher sensitivity. Useful for production-grade monitoring where any change matters.

> 💡 **Engineer mode reminder:** Press `⌘⇧E` to cycle modes any time. Beginner / Builder / Engineer is purely a UI density choice — pipeline contents are identical across modes, so you can switch mid-edit without losing anything.

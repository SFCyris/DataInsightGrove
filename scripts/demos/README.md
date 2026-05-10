# 🔗 Sampling × Join demos

Two real-world use cases that exercise the new sampling methods + the
Join step end-to-end. Idempotent — running twice updates the existing
pipelines instead of duplicating them.

## Run

With the backend up on http://127.0.0.1:8090:

```bash
cd <repo-root>
backend/.venv/bin/python scripts/demos/sampling_join_demos.py
```

The script prints two URLs on success — open them in the editor at
http://localhost:3000.

## Demo 1 — Customer churn × orders, with stratified sampling

**The story.** You're investigating which order patterns correlate
with churn. The raw data has 5,000 customers (only ~12% churned) and
30,000 orders linked by customer_id. You join the two; the result
inherits the imbalance because active customers also order more
frequently. A uniform random sample of the 30,000-row joined table
returns ~3,600 churned-customer rows out of 30,000 — too few to spot
patterns visually.

**Why stratified.** Stratified sampling preserves the class
distribution in the sample. Set `metadata.sampling.method =
"stratified"` with `column = "churn_status"`, and the editor's live
preview shows churned + active rows in their natural proportion of
the joined output (a few hundred churned among the 5,000 sampled rows
— still rare, but visible).

**What's in the pipeline.**
- Two synthetic datasets generated under `data/datasets/`
  (5K customers + 30K orders, deterministic seed).
- A single Join step, inner join on `customer_id`.
- `metadata.sampling = stratified by churn_status, size 5000, seed 42`.

**What to try in the editor.**

1. **Focus the join.** The cardinality strip shows ~5K customers ×
   ~30K orders → ~30K result (1.0× max input — no fan-out, ✓).
2. **Open 🧪 sampling.** See `Stratified by column` is selected with
   `column=churn_status`. Toggle to `Random uniform` for comparison
   and watch the churned-row count in the live grid drop dramatically.
3. **Switch the join's column-collision rule** from `keep_both` to
   `coalesce`. The duplicate `*_year` columns collapse into one.

## Demo 2 — Server requests × incident alerts, with time-bucket sampling

**The story.** You have 28 days of web-server requests (~25K rows)
and a small set of monitoring alerts (~600 rows). You want to LEFT
JOIN them on the hour-truncated timestamp so every request keeps a
flag for "was an alert raised in the same hour?". Traffic is bursty
— hours 9-12 + 18-22 are 5× heavier than off-hours — so a head /
random sample over-represents the busy hours and the live preview
suggests "the system is always busy" when the truth is "busy in 9
hours, quiet in 15."

**Why time-bucket.** Time-bucket sampling partitions by `DATE_TRUNC`
of a timestamp column and keeps N rows per bucket. With `bucket=day,
size=50`, every day in the 28-day range gets exactly 50 rows in the
sample — no oversampling of the dense hours. Trend visualizations
downstream (per-day error rate, alert-correlated request volume)
stay legible.

**What's in the pipeline.**
- Two synthetic datasets generated under `data/datasets/`
  (~25K requests + ~600 alerts, both spanning 2026-01-01 to 01-28).
- A single Join step, LEFT join on hour-truncated `ts_hour`.
- `metadata.sampling = time_bucket on ts_hour, day, size 50, seed 42`.

**What to try in the editor.**

1. **Focus the join.** Auto-detected `ts_hour ↔ ts_hour` suggestion
   should appear (same name, both timestamp, >80% sample overlap).
   Click ➕ to accept.
2. **Cardinality strip.** ~25K requests × ~600 alerts → ~25K result
   (LEFT keeps all requests; most have NO matching alert → NULLs in
   the right side's columns).
3. **Open 🧪 sampling.** See `N rows per time bucket` with `day` +
   `ts_hour`. Switch to `Random uniform` for comparison: random
   over-samples the bursty 9am-12pm + 6pm-10pm windows.
4. **Try `kind=anti_left`** on the icon ladder — surfaces request
   hours that WEREN'T flagged with any alert (most of them).

## Smoke-test results

Both demos verified end-to-end through the same `wrap_with_sampling`
path the live editor uses:

| Demo | Full join | Sampled | Notable |
|---|---|---|---|
| Demo 1 (stratified) | 31,648 rows | 5,000 rows | preserves active/churned ratio |
| Demo 2 (time_bucket) | 28,762 rows | 1,400 rows | exactly 50 rows/day × 28 days |

## Caveats

- **Stratified sample-on-sample weighting** — when the pipeline has
  upstream chained steps before the join, the cardinality strip's
  match% is computed on the sampled rows, not the full data. For an
  imbalanced upstream the match% can read 60-70% even when the full
  join would be 95%+. The strip is labelled "(sample)" to set the
  expectation honestly; future work could swap the estimate for a
  cheap backend-side `count(*)` against the full data.

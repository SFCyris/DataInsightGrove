# ⏳ `time_series_pro` · stationarity + changepoint

**Scenario:** daily traffic for two months, with a deliberate level
shift on Jan 31 — average jumps from ~100 to ~150. The pack should
clearly flag this.

**Data** (`data.csv`, 59 rows): `date, traffic`.

## What the flow shows

```
ds ─┬─→ adf_test            → "non-stationary"  (high p-value)
    ├─→ kpss_test           → "non-stationary"  (low p-value, opposite null)
    ├─→ acf_pacf(15 lags)   → high autocorrelation, slow decay
    └─→ changepoint_detection(thr=4σ)  → flags 2026-01-31 ± a couple of days
```

A series that's truly stationary would have ADF reject H0 (small p) AND
KPSS not reject (large p). Here we expect the opposite of that — the
hallmark of "this needs differencing before you ARIMA it."

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py time_series_pro
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".

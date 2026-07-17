# 🏠 Housing · inventory crunch detection

**Scenario:** 3 years of weekly active-listings counts. The market hit
a sudden supply crunch around week 80 (drop ~1700 listings) lasting
30 weeks, followed by slow recovery (~1100 below baseline) for the
next 20 weeks.

## What the flow shows

```
ds ─┬─→ seasonal_decompose(period=52)        → annual seasonal cycle removed
    ├─→ anomaly_zscore(window=8, thr=2.5σ)   → flags the crunch + recovery weeks
    └─→ changepoint_detection(thr=4σ)        → marks the regime shift week
```

Three diagnostic lenses on the same series: the decomposition shows
the trend bottoming out; the rolling z-score paints individual
anomalous weeks; the changepoint test names the specific week where
the regime changed. Useful for housing-market researchers, mortgage
risk teams, anyone who needs to characterize supply-side shocks.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_housing_inventory_anomaly
```

# 🛍 Retail · weekly sales forecast

**Scenario:** 2 years of weekly unit sales for a retailer. The series has:
- linear growth (~4 units/week trend)
- annual seasonality (peak in December)
- holiday spikes (Black Friday + Christmas, weeks 47-51)
- modest noise

## What the flow shows

```
ds ─┬─→ seasonal_decompose(period=52, additive)  → trend / seasonal / residual chart
    └─→ forecast(horizon=12, holt-winters)        → 12-week forward projection w/ 95% CI
```

The decomposition makes the components visible — you should see a clean
upward trend line, a year-cycle seasonal wave, and small residuals.
The forecast extends 12 weeks past the data with widening confidence
intervals.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_retail_forecast
```

Open the pipeline, click on the forecast node — the ▶ Run on backend
button materialises the chart artifact.

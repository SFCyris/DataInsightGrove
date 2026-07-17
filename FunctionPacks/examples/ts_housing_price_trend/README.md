# 🏠 Housing · monthly price trend forecast

**Scenario:** 5 years of monthly median home prices for two cities.
Austin had explosive growth that plateaued late; Boston had steady
modest growth.

## What the flow shows

```
ds ─→ filter_rows(city = 'Austin')      → drop Boston for the forecast view
   ─→ forecast(horizon=12, period=12)   → next year w/ 95% CI
```

The Holt-Winters method handles the trend bend better than a naive
linear extrapolation — the prediction interval widens as we project
further out, making the uncertainty visible.

## Try also

Switch the filter to `city = 'Boston'` to see the comparison; or
remove the filter and pipe the full series through `seasonal_decompose`
to see the 12-month seasonal component each city has.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_housing_price_trend
```

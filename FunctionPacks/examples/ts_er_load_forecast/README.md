# 🚑 Healthcare · ER load forecast

**Scenario:** Hourly ER admissions over a 28-day window (672 rows).
Strong daily pattern (peak 10pm-2am, dip 4am-7am) plus a weekend
weekend-evening bump.

## What the flow shows

```
ds ─┬─→ seasonal_decompose(period=24)            → daily-cycle visible
    └─→ forecast(horizon=168, period=24)         → next 7 days w/ 95% CI
```

Staffing decisions hang on knowing what the next overnight shift will
look like. The 24-hour seasonal period extrapolates the daily pattern;
the noise band (residuals) sets the staffing buffer.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_er_load_forecast
```

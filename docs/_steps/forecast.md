**When to use:** project a daily/weekly/monthly time series N steps into the future, with prediction intervals.

**Example:** 30-day stock close forecast.

```json
{
  "step": "forecast",
  "params": {
    "time_column": "date",
    "value_column": "close",
    "horizon": 30,
    "method": "holt_winters",
    "seasonal_period": 7
  }
}
```

The output extends the input frame: existing rows get `forecast = null`, new future rows have `forecast` + `forecast_lo` / `forecast_hi` 95% prediction intervals. The artifact image overlays observed + forecast + shaded interval:

![stock forecast](images/tutorials/tutorial-forecast-stock.png)

**Method selection:** `auto` picks `holt_winters` when the seasonal period is plausible, else `ets`. Set explicitly for reproducibility. `naive` (last-observation-carried-forward) is the baseline you should beat.

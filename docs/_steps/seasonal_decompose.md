**When to use:** understand why a time series looks the way it does — separate the slow trend, the periodic seasonal pattern, and the residual noise.

**Example:** is the recent uptick in our daily revenue real growth, or just the typical month-end seasonal bump?

```json
{
  "step": "seasonal_decompose",
  "params": {
    "time_column": "date",
    "value_column": "revenue",
    "model": "additive",
    "period": 7
  }
}
```

The output adds `trend`, `seasonal`, `residual` columns. The rendered 4-panel plot lets you eyeball the decomposition:

![seasonal decomposition](images/tutorials/tutorial-seasonal-stock.png)

Use `additive` when seasonal amplitude is roughly constant over time; `multiplicative` when the swings grow / shrink with the level (e.g. growing exponential trend).

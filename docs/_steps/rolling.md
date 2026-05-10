**When to use:** smooth a noisy time series, or look at a rolling sum / max / std deviation over a window.

**Example:** 7-day moving average of daily revenue.

```json
{
  "step": "rolling",
  "params": {
    "time_column": "date",
    "windows": [
      {"column": "revenue", "fn": "mean", "window": "7d", "as": "revenue_ma7"},
      {"column": "revenue", "fn": "max",  "window": "7d", "as": "revenue_max7"}
    ],
    "min_periods": 3
  }
}
```

**Two flavors of `window`:**

- **Time-based** (e.g. `"7d"`, `"24h"`) — uses the time column to define the window. Handles uneven spacing correctly.
- **Row-based** (an integer like `7`) — windows over the previous N rows regardless of time. Faster but assumes evenly-sampled data.

`min_periods` controls when the rolling output starts emitting a value — useful to avoid noisy values from the very first few observations.

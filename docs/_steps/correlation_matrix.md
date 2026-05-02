**When to use:** quick sanity check before modeling — which numeric columns move together, which are independent, which redundant.

**Example:** stock returns. Compute pairwise correlation across 5 tickers' close-price columns; spot any pair with |r| > 0.9 that you can drop or combine.

```json
{
  "step": "correlation_matrix",
  "params": {
    "columns": ["AAPL", "MSFT", "NVDA", "AMD", "GOOG"],
    "method": "pearson",
    "title": "Tech basket — daily returns"
  }
}
```

**Output:** a long-form `(col_a, col_b, r)` table you can filter further. The rendered heatmap is added to the run's artifacts panel.

![correlation heatmap](images/tutorials/tutorial-pca-flowers.png)

(Sample image is from PCA — the correlation heatmap looks similar but with red/blue divergent palette centered at 0.)

**When to use:** group customers / products / sensors into K behavioral clusters. Output is a new `cluster` column you can join back, filter, or render.

**Example:** segment customers by spend + tenure.

```json
{
  "step": "kmeans",
  "params": {
    "columns": ["monthly_revenue", "tenure_days"],
    "k": 4,
    "scale": true,
    "output_column": "segment"
  }
}
```

If you give kmeans more than 2 features, the auto-rendered scatter projects via PCA so you can still visualize the clusters. The cluster summary (sizes, inertia) lands in the run's artifacts panel.

**Tip:** combine with `correlation_matrix` and the `kmeans` `inertia` metric across several values of K (the elbow heuristic) to pick K. DIG's `k` param doesn't auto-pick K — that's a deliberate decision so you can see the trade-off, not a magic number.

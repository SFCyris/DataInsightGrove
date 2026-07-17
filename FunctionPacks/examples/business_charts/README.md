# 📈 `business_charts` · revenue dashboard

**Scenario:** three quick visualisations a finance / ops team would
present at a board meeting. Each comes from its own small CSV.

**Data**:
- `data_bridge.csv` — Q1 starting balance plus signed deltas (new
  customers, upsells, churn, discounts, refunds). Feeds the waterfall.
- `data_pareto.csv` — product-level revenue. Feeds the Pareto.
- `data_funnel.csv` — funnel stages from landing page → activated. Feeds
  the funnel chart.

## What the flow shows

```
ds_bridge  → waterfall_chart   → "where did Q2 revenue come from / go to?"
ds_pareto  → pareto_chart      → "which products drive 80% of revenue?"
ds_funnel  → funnel_chart      → "where do new users drop off?"
```

Each step writes a PNG artifact and passes the input through unchanged.

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py business_charts
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".

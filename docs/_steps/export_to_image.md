**When to use:** end of a pipeline, when you want a chart you can paste into a slide / share / embed in a report.

DIG renders via matplotlib + seaborn — not a web charting library — so the output is publication-grade PNG (or SVG). No JS bundle weight, deterministic, headless-friendly.

**Auto-pick logic:** with `kind = "auto"` the step inspects the columns you fill in plus their types and picks a sensible chart:

| You fill | Types | Auto-picked chart |
|---|---|---|
| 1 axis | numeric | histogram (with KDE) |
| 1 axis | categorical | top-N horizontal bar |
| 2 axes | num × num | scatter |
| 2 axes | cat × num | bar (mean per category) |
| 3 axes | x × y × value | heatmap (pivot) |
| 3 axes | all numeric | 3-D scatter |

**Example — bar chart:**

```json
{
  "step": "export_to_image",
  "params": {
    "kind": "bar_counts",
    "x": "region",
    "title": "💰 Revenue by region"
  }
}
```

![bar chart by region](images/tutorials/tutorial-bar-by-region.png)

**Example — heatmap (region × product):**

```json
{
  "step": "export_to_image",
  "params": {
    "kind": "heatmap",
    "x": "region",
    "y4": "product",
    "value": "revenue",
    "title": "🔥 Revenue heatmap"
  }
}
```

![heatmap region × product](images/tutorials/tutorial-heatmap-sales.png)

**Tip:** the file is written under `data/outputs/<run_id>/<step>.png` by default. Set `path` to override (relative paths are resolved against the run dir; absolute paths land where you put them).

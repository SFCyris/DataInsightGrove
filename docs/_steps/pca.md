**When to use:** dataset has many numeric columns and you want a 2-D view that captures most of the variance. PCA is fast, deterministic, linear — best baseline for "what does my data look like?".

**Example:** flowers dataset (`samples/flowers-demo.csv`). Project the 4 morphological measurements onto 2 components, color by species.

```json
{
  "step": "pca",
  "params": {
    "columns": ["petal_length", "petal_width", "sepal_length", "sepal_width"],
    "n_components": 2,
    "color_by": "species",
    "title": "Flowers — PCA"
  }
}
```

The output frame keeps every row and adds `PC1`, `PC2` columns. The rendered scatter shows the components labeled with variance explained:

![PCA scatter](images/tutorials/tutorial-pca-flowers.png)

When >2 components are useful, raise `n_components` — the additional `PC3..PCK` columns are still added to the data, you can use them for downstream `kmeans` / `linear_regression` etc.

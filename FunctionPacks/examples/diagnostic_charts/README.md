# 📊 `diagnostic_charts` · A vs B distribution dossier

**Scenario:** two groups A and B with the same mean (~100) but very
different distributions. Group A is tightly normal; group B has heavy
tails — extreme values at 68, 75, 140, 150. A naive comparison of
means would say "they look the same." The diagnostic charts show
they're not.

**Data** (`data.csv`, 50 rows): `id, group, measurement`.

## What the flow shows

```
ds ─┬─→ box_plot(value, group)                  → median + whiskers + outlier dots
    ├─→ violin_plot(value, group)               → KDE + box hybrid; heavy tails are visible
    ├─→ filter(group=B) → qq_plot(value)        → S-shape vs the diagonal = fat tails
    └─→ ecdf_plot(value, group)                 → curve B is flatter at the extremes
```

Each step writes a PNG artifact and passes the input data through
unchanged — chain them all on a single dataset to produce a four-image
diagnostic dossier in one run.

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py diagnostic_charts
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".

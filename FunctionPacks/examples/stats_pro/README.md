# 📐 `stats_pro` · A/B/C test demo

**Scenario:** an e-commerce site tests three checkout-button colors
(red / green / blue). For each user we record whether they converted
and how much they spent.

**Data** (`data.csv`, 45 rows): `user_id, checkout_button_color, converted, revenue`.

## What the flow shows

```
ds ─┬─→ anova(revenue ~ color)                    → "is there ANY group difference?"
    ├─→ filter(red+blue) → mann_whitney            → "red vs blue (non-parametric)"
    ├─→ filter(green+blue) → effect_size           → "how big is green vs blue?"
    └─→ bootstrap_ci(revenue, mean, 95%)           → "what's our uncertainty around the mean?"
```

| Node | Pack step | Question |
|------|-----------|----------|
| `n_anova` | `stats_pro/anova` | Do any of the three colors have different mean revenue? |
| `n_mw` | `stats_pro/mann_whitney` | Red vs blue without assuming normality |
| `n_eff` | `stats_pro/effect_size` | Cohen's d / Hedges' g for green vs blue |
| `n_boot` | `stats_pro/bootstrap_ci` | 95% CI around overall mean revenue |

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py stats_pro
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".

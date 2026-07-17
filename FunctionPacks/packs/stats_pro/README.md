# 📐 Statistics Pro

The full inferential-statistics toolbox. Pairs with the basic `statspack`
(t_test + ks_test) — install both for the complete kit.

## Steps

| Step | Purpose |
| --- | --- |
| `chi_square` | Chi-squared test of independence on a contingency table |
| `anova`      | One-way ANOVA across N groups |
| `mann_whitney` | Mann-Whitney U (non-parametric two-sample) |
| `effect_size` | Cohen's d, Hedges' g, Cramér's V, η² |
| `multiple_comparison_correction` | Bonferroni / Holm / Benjamini-Hochberg FDR on a column of p-values |
| `bootstrap_ci` | Distribution-free CIs around mean / median / arbitrary statistic |

## Requirements

```bash
pip install "scipy>=1.11" "statsmodels>=0.14"
```

DIG installs these automatically when you install the pack.

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.

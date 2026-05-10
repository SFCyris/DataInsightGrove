# 📐 Statistics Pack

A small bundle of inferential-statistics steps for DIG. Drop into your
running DIG instance via Settings → Step Packs.

## What's inside

| Step | Purpose |
| --- | --- |
| `t_test`   | Two-sample independent (Welch's) t-test — does the mean of column X differ between two groups? |
| `ks_test`  | Two-sample Kolmogorov-Smirnov test — do two groups have the same distribution at all? |

Each step takes a *value* column and a *group* column with exactly two
distinct values, and produces a one-row result with the test statistic,
p-value, degrees of freedom (where applicable), and per-group sample
sizes.

## Requirements

```bash
pip install "scipy>=1.11"
```

scipy is already a transitive dependency of DIG's built-in time-series
features, so on a stock install you typically don't need to do anything.
If you see `ModuleNotFoundError: scipy` after a pack install, run the
above in your DIG Python environment.

## Examples

After installing, search the picker for `t-test`, `ttest`, or `compare
means`. Drop the `📐 Two-sample t-test` step downstream of a node whose
schema has at least one numeric column and one binary categorical
column.

## Changelog

### 0.1.0 — 2026-05-05

- Initial release: `t_test`, `ks_test`.

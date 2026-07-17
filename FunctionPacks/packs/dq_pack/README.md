# 🛡 Data Quality

Production-grade data-quality steps that go beyond `expectations`:
distribution drift, outlier flagging, and null-pattern audits.

## Steps

| Step | Purpose |
| --- | --- |
| `psi_drift`                   | Population Stability Index between two distributions of the same column |
| `outliers_iqr`                | Tukey-fence outlier flag per row (IQR-based, distribution-free) |
| `outliers_isolation_forest`   | Multivariate outlier flag using Isolation Forest |
| `null_pattern_audit`          | Per-column null counts + pairwise null co-occurrence |

## Requirements

```bash
pip install "scikit-learn>=1.3"
```

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.

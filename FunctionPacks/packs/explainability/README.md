# 🔍 Explainability

Model-agnostic feature-importance + partial-dependence steps.

Each step internally fits a gradient-boosted regressor (numeric target)
or classifier (categorical target) and runs the explainer against that
quick model. This means you don't need a pre-fitted model from elsewhere
— pass in raw features + target and the pack does the rest.

## Steps

| Step | Purpose |
| --- | --- |
| `permutation_importance` | Feature ranking by drop in score when each feature is shuffled |
| `partial_dependence`     | Average predicted target as a feature varies — long-form output for plotting |

## Requirements

```bash
pip install "scikit-learn>=1.3"
```

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.

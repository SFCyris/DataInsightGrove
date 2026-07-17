# 🔍 `explainability` · which features matter?

**Scenario:** synthetic credit-default dataset. We deliberately
constructed it so:
- `n_late_payments`, `credit_score`, `years_employed` actually predict default
- `age`, `income` are weakly predictive
- `noise_a`, `noise_b` are pure random noise

The pack should rank the real features at the top and place noise at the bottom.

**Data** (`data.csv`, 40 rows): `id, age, income, credit_score,
n_late_payments, years_employed, noise_a, noise_b, defaulted`.

## What the flow shows

```
ds ─┬─→ permutation_importance(7 features, target=defaulted)
    └─→ partial_dependence(explain=n_late_payments)
```

Expected ranking from `permutation_importance`:
1. `n_late_payments`
2. `credit_score`
3. `years_employed`
4. `age` / `income` (correlated with the above, low marginal importance)
5. `noise_a`, `noise_b` near zero

`partial_dependence` for `n_late_payments` should show the predicted
default probability rising monotonically with the count.

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py explainability
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".

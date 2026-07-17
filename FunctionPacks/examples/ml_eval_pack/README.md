# 🧪 `ml_eval_pack` · churn-model evaluation

**Scenario:** evaluate a binary churn classifier off-line. The dataset
already contains the model's predictions + probability score.

**Data** (`data.csv`, 50 rows): `customer_id, actual_churn, predicted_churn, churn_probability`.

## What the flow shows

```
ds → train_test_split (stratified) → filter(split='test')
                                       ├─→ model_metrics (acc/F1/AUC/log-loss)
                                       ├─→ confusion_matrix
                                       └─→ roc_curve (points + AUC)
```

| Node | Step | Outcome |
|------|------|---------|
| `n_split` | `ml_eval_pack/train_test_split` | 70/30 split, stratified by `actual_churn` |
| `n_metrics` | `ml_eval_pack/model_metrics` | Accuracy, precision, recall, F1, ROC AUC, log-loss |
| `n_cm` | `ml_eval_pack/confusion_matrix` | Per-class counts + row-normalized rates |
| `n_roc` | `ml_eval_pack/roc_curve` | (FPR, TPR, threshold) ready to plot |

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py ml_eval_pack
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".

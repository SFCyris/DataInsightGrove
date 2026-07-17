# Step-Pack examples

One demo flow per pack, each in its own subdirectory:

- `data.csv` (or several CSVs named `data_<name>.csv`) — sample input
- `flow.dig.json` — pipeline document with **placeholders** for dataset references
- `README.md` — scenario, expected outcomes, how to load

The flows are designed to be **illustrative**, not exhaustive — each
shows the pack's signature steps on data where the result is visible
and intuitive (drift in `dq_pack`, regime shift in `time_series_pro`,
clean cluster split in `embedding_search`, etc.).

## Quick start — one command per example

The fastest path is `scripts/import_example.py`. It uploads the CSV(s),
substitutes the placeholders in `flow.dig.json`, and creates the
pipeline in your running DIG. **Make sure the pack is installed first**
(Settings → Step Packs).

```bash
# Backend must be running on http://127.0.0.1:8190 (override with DIG_API=…).
python3 FunctionPacks/scripts/import_example.py stats_pro

# Or import every example at once:
python3 FunctionPacks/scripts/import_example.py --all
```

Each import prints the pipeline URL. Open it in your browser.

## Why placeholders?

DIG's frontend reverse-looks-up dataset references using the convention
`ds_<dataset-ulid-lowercase>`. If you wrote a literal `"ds"` alias the
chip would render but the grid + profile preview would stay empty.
The placeholder format keeps the JSON portable across machines and lets
the importer fill in the right value:

| Placeholder | Substituted with |
|---|---|
| `{{DATASET_ID}}` | `ds_<ulid_lowercased>` of the uploaded `data.csv` |
| `{{DATASET_URI}}` | `file:///…/data/datasets/<ULID>.parquet` |
| `{{DATASET_<NAME>_ID}}` | matching CSV named `data_<name>.csv` (multi-dataset flows) |
| `{{DATASET_<NAME>_URI}}` | same |

`business_charts` is the only multi-dataset example — its three CSVs
(`data_revenue_bridge.csv`, `data_pareto.csv`, `data_funnel.csv`) map to
`{{DATASET_REVENUE_BRIDGE_ID}}`, `{{DATASET_PARETO_ID}}`, and
`{{DATASET_FUNNEL_ID}}` respectively.

## Index

| Pack | Demo scenario | Steps used | Notable in data |
|------|---------------|------------|-----------------|
| [📐 stats_pro](stats_pro/) | A/B/C button-color test | anova, mann_whitney, effect_size, bootstrap_ci | green clearly outperforms red and blue |
| [🧪 ml_eval_pack](ml_eval_pack/) | Churn-model evaluation | train_test_split, model_metrics, confusion_matrix, roc_curve | ~80% accuracy, AUC ~0.93 |
| [🛡 dq_pack](dq_pack/) | Drift + outliers + null audit | psi_drift, outliers_iqr, outliers_isolation_forest, null_pattern_audit | ~50% PSI between baseline / current |
| [⏳ time_series_pro](time_series_pro/) | Daily traffic, regime shift | adf_test, kpss_test, acf_pacf, changepoint_detection | level shift on 2026-01-31 |
| [📅 dates_pack](dates_pack/) | Order processing dates | fiscal_year_parts, business_days_between, date_snap | orders spanning Christmas / NY |
| [🔧 units_pro](units_pro/) | Sensor unit normalisation | convert_units_pro, physical_constant | mixed °C/miles/psi/kWh |
| [📞 formats_pack](formats_pack/) | CRM contact hygiene | normalize_phone, validate_email, validate_iban | broken rows for each format |
| [📚 reference_data](reference_data/) | International users canonicalised | country_lookup, currency_lookup, timezone_resolve | mixed alpha-2 / alpha-3 / numeric / name |
| [✨ llm_augment](llm_augment/) | Support-ticket triage | llm_classify, llm_extract, llm_summarize | requires AI configured |
| [🧭 embedding_search](embedding_search/) | Three-topic doc clustering | semantic_cluster, nearest_neighbors | toy 3-D embeddings, clean separation |
| [🔍 explainability](explainability/) | Credit-default feature ranking | permutation_importance, partial_dependence | known signal vs noise features |
| [📊 diagnostic_charts](diagnostic_charts/) | Distribution dossier (A vs B) | box_plot, violin_plot, qq_plot, ecdf_plot | A normal, B heavy-tailed |
| [📈 business_charts](business_charts/) | Revenue waterfall + Pareto + funnel | waterfall_chart, pareto_chart, funnel_chart | three small CSVs |

## Manual recreation (alternative)

If you'd rather build the flow by hand:

1. Install the pack via Settings → Step Packs (drop the matching
   `.dpack` from `FunctionPacks/dist/`).
2. Upload the example's CSV(s) as DIG datasets.
3. Create a pipeline, drag in the example's CSV as the dataset.
4. Add each step from `flow.dig.json` in order, copying the `params`
   block. The `inputs` section tells you which upstream node feeds this
   one.

Each example's `README.md` has a flow diagram + per-node "what it
shows" table to make this fast.

## Writing a new example

```bash
mkdir -p FunctionPacks/examples/<pack_id>
# add data.csv + flow.dig.json + README.md
```

In the `flow.dig.json`:

- Use `{{DATASET_ID}}` and `{{DATASET_URI}}` for single-dataset flows.
- For multiple datasets, name each CSV `data_<name>.csv` and use
  `{{DATASET_<NAME>_ID}}` / `{{DATASET_<NAME>_URI}}`. The importer
  matches on the filename suffix.
- `connector: "csv"` for the dataset record (the importer rewrites this
  to the parquet storage URI at substitution time).
- `stepVersion: "1.0.0"` for every node referencing a 1.0.0 pack step.

Then run `python3 FunctionPacks/scripts/import_example.py <pack_id>`
to verify it imports cleanly.

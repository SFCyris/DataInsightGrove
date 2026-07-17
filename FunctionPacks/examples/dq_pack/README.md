# 🛡 `dq_pack` · drift + outliers + null audit

**Scenario:** a product analytics team compares two weekly snapshots —
baseline vs current — to detect whether engagement metrics have shifted
or broken. The data has injected drift, two extreme outliers, and a
sprinkling of nulls.

**Data** (`data.csv`, 50 rows): `user_id, partition, session_minutes,
pages_per_session, signups_today`. Engagement values are visibly higher
in the `current` partition — PSI should flag this.

## What the flow shows

```
ds ─┬─→ psi_drift(session_minutes)            → "did session length drift?"
    ├─→ psi_drift(pages_per_session)          → "did engagement drift?"
    ├─→ outliers_iqr(session_minutes)         → row-level IQR-fence flag
    ├─→ outliers_isolation_forest(2 cols)     → multivariate outlier flag
    └─→ null_pattern_audit                    → "do nulls cluster?"
```

| Node | Step | Outcome |
|------|------|---------|
| `n_psi_session` | `dq_pack/psi_drift` | PSI > 0.25 → "significant drift" |
| `n_iqr` | `dq_pack/outliers_iqr` | Flags rows with `session_minutes` outside Tukey fences |
| `n_iso` | `dq_pack/outliers_isolation_forest` | Catches the 99-min and 180-min spikes that look anomalous *given* their pages-per-session co-value |
| `n_nulls` | `dq_pack/null_pattern_audit` | Reports the rows where multiple columns are null together |

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py dq_pack
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".

# 🏥 Healthcare · readmission rate trend + intervention

**Scenario:** Monthly 30-day-readmission rate at a hospital, 4 years
(48 months). The series has a slow downward trend, winter seasonality
(higher rates in cold months), and a quality-improvement intervention
at month 30 that drops the baseline by ~2.3 percentage points.

## What the flow shows

```
ds ─┬─→ seasonal_decompose(period=12)  → trend reveals the intervention drop
    └─→ changepoint_detection(thr=4σ)  → flags the month-30 shift
```

The decomposition's trend panel is what hospital admins look at to
verify a QI intervention "worked" — the changepoint flag confirms it
quantitatively. Both signals point at month 30 ± 1.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_hospital_readmissions
```

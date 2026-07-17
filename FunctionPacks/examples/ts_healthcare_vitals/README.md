# 🏥 Healthcare · vitals anomaly detection

**Scenario:** Continuous monitoring stream — 1 sample every 30 seconds
for 6 hours (720 rows). Three vital signs: heart rate, SpO₂, systolic
blood pressure. Two synthetic alert windows are baked in:
- minutes 100-115: tachycardia (HR +35 bpm)
- minutes 240-255: desaturation (SpO₂ -5%, HR +18 bpm)

## What the flow shows

```
ds ─→ anomaly_zscore(value=heart_rate_bpm)  → flags both windows
   ─→ export_to_image (3 vitals overlaid)    → multi-line chart
```

For ICU monitoring or remote-patient-monitoring contexts, the
rolling-window approach is what catches *physiologically meaningful*
anomalies vs. just data-collection noise. Replace the chart kind with
`scatter` and paint `is_anomaly` to highlight the alert windows.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_healthcare_vitals
```

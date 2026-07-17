# 🏭 IoT · sensor anomaly detection

**Scenario:** 8-hour shift on a factory machine, 1 reading per minute
(480 rows). Vibration drifts slowly upward as bearings warm; three
deliberate anomalous bursts are injected at minutes 110, 250, 380.

## What the flow shows

```
ds ─→ anomaly_zscore(window=60, threshold=3σ)  → adds zscore + is_anomaly
   ─→ export_to_image                            → scatter w/ red anomaly markers
```

The rolling z-score is robust to the slow upward drift — a global
z-score would either flag every late-shift point as "anomalous" or miss
the early bursts. With a 60-minute window, the anomaly threshold
adapts to the local baseline and only the 3 spikes are flagged.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_iot_anomaly
```

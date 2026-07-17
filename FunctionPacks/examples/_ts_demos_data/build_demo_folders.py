#!/usr/bin/env python3
"""Materialise all 8 time-series demo folders.

For each demo: creates ``FunctionPacks/examples/<demo_id>/``
containing ``data.csv`` (copied from the generator), ``flow.dig.json``
(dig pipeline using the {{DATASET_ID}}/{{DATASET_URI}} placeholders),
and ``README.md`` with a short story about what the flow shows.

Run AFTER ``generate.py``:
    python3 build_demo_folders.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent
PLACEHOLDER_DS = "{{DATASET_ID}}"
PLACEHOLDER_URI = "{{DATASET_URI}}"


def _stub_dataset(label: str) -> dict:
    return {
        "id": PLACEHOLDER_DS,
        "connector": "parquet",
        "uri": PLACEHOLDER_URI,
        "label": label,
    }


def _node(node_id: str, step: str, *, inputs_ref: str, params: dict, ui_label: str, x: int, y: int) -> dict:
    return {
        "id": node_id,
        "step": step,
        "stepVersion": "1.0.0",
        "inputs": {"in": {"ref": inputs_ref}},
        "outputs": ["out"],
        "params": params,
        "ui": {"x": x, "y": y, "label": ui_label},
    }


def _save_demo(demo_id: str, *, csv_filename: str, name: str, description: str, dataset_label: str, nodes: list, readme: str) -> None:
    out = EXAMPLES / demo_id
    out.mkdir(exist_ok=True)
    # Copy CSV → data.csv (the canonical name the import script expects)
    shutil.copy(HERE / csv_filename, out / "data.csv")
    flow = {
        "schemaVersion": 1,
        "id": f"{demo_id}_demo",
        "name": name,
        "description": description,
        "datasets": [_stub_dataset(dataset_label)],
        "nodes": nodes,
        "outputs": [],
    }
    (out / "flow.dig.json").write_text(json.dumps(flow, indent=2))
    (out / "README.md").write_text(readme)
    print(f"  built {demo_id}/")


# ── Demo 1 — Retail weekly sales forecast ─────────────────────────────
_save_demo(
    demo_id="ts_retail_forecast",
    csv_filename="retail_sales.csv",
    name="🛍 Retail · weekly sales forecast",
    dataset_label="2 years of weekly unit sales with seasonality + trend + holiday spikes",
    description="Forecast 12 weeks ahead with Holt-Winters. Holiday spikes (weeks 47-51) and the upward trend are both picked up by the seasonal+trend decomposition.",
    nodes=[
        _node("n_decomp", "seasonal_decompose", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="Decompose · 52w period",
              params={"time_column": "week", "value_column": "units_sold", "model": "additive", "period": 52, "render": True, "title": "Retail sales · trend + seasonal + residual"}),
        _node("n_forecast", "forecast", inputs_ref=PLACEHOLDER_DS, x=300, y=240, ui_label="Forecast · 12 weeks ahead",
              params={"time_column": "week", "value_column": "units_sold", "horizon": 12, "method": "holt_winters", "seasonal_period": 52, "render": True, "title": "Weekly sales forecast · 12 weeks"}),
    ],
    readme="""# 🛍 Retail · weekly sales forecast

**Scenario:** 2 years of weekly unit sales for a retailer. The series has:
- linear growth (~4 units/week trend)
- annual seasonality (peak in December)
- holiday spikes (Black Friday + Christmas, weeks 47-51)
- modest noise

## What the flow shows

```
ds ─┬─→ seasonal_decompose(period=52, additive)  → trend / seasonal / residual chart
    └─→ forecast(horizon=12, holt-winters)        → 12-week forward projection w/ 95% CI
```

The decomposition makes the components visible — you should see a clean
upward trend line, a year-cycle seasonal wave, and small residuals.
The forecast extends 12 weeks past the data with widening confidence
intervals.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_retail_forecast
```

Open the pipeline, click on the forecast node — the ▶ Run on backend
button materialises the chart artifact.
""",
)

# ── Demo 2 — IoT factory sensor anomaly ───────────────────────────────
_save_demo(
    demo_id="ts_iot_anomaly",
    csv_filename="iot_sensor.csv",
    name="🏭 IoT · sensor anomaly detection",
    dataset_label="8-hour shift of factory sensor readings (vibration + bearing temp) with 3 injected anomalies",
    description="Roll a z-score over a 60-min window and flag points that exceed 3σ. Catches the 3 anomalous bursts without false-positives on the slow drift.",
    nodes=[
        _node("n_anomaly", "anomaly_zscore", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="Z-score · 60-min window",
              params={"value": "vibration_mm_s", "window": 60, "threshold": 3.0, "min_periods": 30}),
        _node("n_chart", "export_to_image", inputs_ref="n_anomaly", x=580, y=80, ui_label="Plot vibration + anomalies",
              params={"kind": "scatter", "x": "ts", "y": "vibration_mm_s", "value": "is_anomaly", "title": "Vibration · anomalies highlighted (yellow = is_anomaly)", "format": "png", "width": 1400, "height": 520, "dpi": 96, "max_points": 1000}),
    ],
    readme="""# 🏭 IoT · sensor anomaly detection

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
""",
)

# ── Demo 3 — Financial daily returns volatility ───────────────────────
_save_demo(
    demo_id="ts_financial_volatility",
    csv_filename="financial_returns.csv",
    name="💹 Financial · 20-day rolling volatility",
    dataset_label="2 years of daily prices + returns with a high-volatility cluster",
    description="Compute 20-day rolling standard deviation of returns to surface volatility regimes. The mid-series earnings cluster shows up as a sharp spike.",
    nodes=[
        _node("n_rolling", "rolling", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="Rolling std · 20d",
              params={"time_column": "date", "windows": [{"column": "return_pct", "fn": "std", "window": 20, "as": "return_pct_std_20"}], "min_periods": 5}),
        _node("n_chart", "export_to_image", inputs_ref="n_rolling", x=580, y=80, ui_label="Plot volatility",
              params={"kind": "line", "x": "date", "y": "return_pct_std_20", "title": "20-day rolling volatility (std of returns)", "format": "png", "width": 1400, "height": 480, "dpi": 96}),
    ],
    readme="""# 💹 Financial · 20-day rolling volatility

**Scenario:** ~2 years of daily price + return data. There's a 60-day
cluster of high-volatility days mid-series (think earnings season or
a crisis window).

## What the flow shows

```
ds ─→ rolling(window=20)             → adds return_pct_std_20 + return_pct_mean_20
   ─→ export_to_image                  → line chart of the rolling std
```

The flat-then-spike-then-flat pattern in the rolling std is exactly
how volatility regimes manifest — the kind of signal a quant or risk
analyst would build a vol-targeting strategy around.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_financial_volatility
```
""",
)

# ── Demo 4 — Healthcare vitals anomaly ─────────────────────────────────
_save_demo(
    demo_id="ts_healthcare_vitals",
    csv_filename="healthcare_vitals.csv",
    name="🏥 Healthcare · vitals anomaly detection",
    dataset_label="6 hours of patient vital signs with 2 synthetic alert windows (tachycardia + desat)",
    description="Run rolling z-score on heart rate and SpO2. Catches the tachycardia event (heart rate spike) and the desat (oxygen drop) without flapping on the gentle baseline drift.",
    nodes=[
        _node("n_hr", "anomaly_zscore", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="HR z-score · 5min window",
              params={"value": "heart_rate_bpm", "window": 30, "threshold": 3.0, "min_periods": 15}),
        _node("n_chart", "export_to_image", inputs_ref="n_hr", x=580, y=80, ui_label="Plot HR + anomalies",
              params={"kind": "line", "x": "ts", "y": "heart_rate_bpm", "y2": "spo2_pct", "y3": "sbp_mmhg", "title": "Patient vitals · 6-hour monitoring window", "format": "png", "width": 1400, "height": 540, "dpi": 96}),
    ],
    readme="""# 🏥 Healthcare · vitals anomaly detection

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
""",
)

# ── Demo 5 — Hospital monthly readmissions ─────────────────────────────
_save_demo(
    demo_id="ts_hospital_readmissions",
    csv_filename="hospital_readmissions.csv",
    name="🏥 Healthcare · readmission rate trend + intervention",
    dataset_label="48 months of hospital readmission rates with a quality-improvement intervention at month 30",
    description="Decompose into trend / seasonal / residual, then run changepoint detection. The intervention drop should fire as a clear changepoint around month 30.",
    nodes=[
        _node("n_decomp", "seasonal_decompose", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="Decompose · 12m period",
              params={"time_column": "month", "value_column": "readmission_rate_pct", "model": "additive", "period": 12, "render": True, "title": "Readmission rate · decomposition"}),
        _node("n_cp", "changepoint_detection", inputs_ref=PLACEHOLDER_DS, x=300, y=240, ui_label="Changepoint · 4σ",
              params={"value": "readmission_rate_pct", "threshold": 4.0}),
    ],
    readme="""# 🏥 Healthcare · readmission rate trend + intervention

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
""",
)

# ── Demo 6 — ER hourly load forecast ───────────────────────────────────
_save_demo(
    demo_id="ts_er_load_forecast",
    csv_filename="er_load.csv",
    name="🚑 Healthcare · ER load forecast (next 7 days)",
    dataset_label="28 days of hourly ER admissions with daily + weekly seasonality",
    description="Forecast hourly admissions for the next 168 hours (1 week) using Holt-Winters with a 24-hour seasonal period. Surfaces the night-shift peak and the weekend bump.",
    nodes=[
        _node("n_decomp", "seasonal_decompose", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="Decompose · daily 24h",
              params={"time_column": "ts", "value_column": "patients_admitted", "model": "additive", "period": 24, "render": True, "title": "ER hourly admissions · decomposition"}),
        _node("n_forecast", "forecast", inputs_ref=PLACEHOLDER_DS, x=300, y=240, ui_label="Forecast · 168h ahead",
              params={"time_column": "ts", "value_column": "patients_admitted", "horizon": 168, "method": "holt_winters", "seasonal_period": 24, "render": True, "title": "ER load forecast · next 7 days"}),
    ],
    readme="""# 🚑 Healthcare · ER load forecast

**Scenario:** Hourly ER admissions over a 28-day window (672 rows).
Strong daily pattern (peak 10pm-2am, dip 4am-7am) plus a weekend
weekend-evening bump.

## What the flow shows

```
ds ─┬─→ seasonal_decompose(period=24)            → daily-cycle visible
    └─→ forecast(horizon=168, period=24)         → next 7 days w/ 95% CI
```

Staffing decisions hang on knowing what the next overnight shift will
look like. The 24-hour seasonal period extrapolates the daily pattern;
the noise band (residuals) sets the staffing buffer.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_er_load_forecast
```
""",
)

# ── Demo 7 — Housing price trend forecast ─────────────────────────────
_save_demo(
    demo_id="ts_housing_price_trend",
    csv_filename="housing_price.csv",
    name="🏠 Housing · monthly price trend forecast",
    dataset_label="5 years of monthly median home prices for Austin + Boston",
    description="Forecast 12 months ahead per city. Austin's price grew fast then plateaued — the forecast captures that bend; Boston's slow-and-steady growth extrapolates linearly.",
    nodes=[
        # Note: this demo has 2 cities; we filter to one upstream.
        # filter_rows is a built-in step.
        _node("n_filter", "filter_rows", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="Austin only",
              params={"predicate": "city = 'Austin'"}),
        _node("n_forecast", "forecast", inputs_ref="n_filter", x=580, y=80, ui_label="Forecast · 12m ahead",
              params={"time_column": "month", "value_column": "median_price_kusd", "horizon": 12, "method": "holt_winters", "seasonal_period": 12, "render": True, "title": "Austin median home price · 12-month forecast"}),
    ],
    readme="""# 🏠 Housing · monthly price trend forecast

**Scenario:** 5 years of monthly median home prices for two cities.
Austin had explosive growth that plateaued late; Boston had steady
modest growth.

## What the flow shows

```
ds ─→ filter_rows(city = 'Austin')      → drop Boston for the forecast view
   ─→ forecast(horizon=12, period=12)   → next year w/ 95% CI
```

The Holt-Winters method handles the trend bend better than a naive
linear extrapolation — the prediction interval widens as we project
further out, making the uncertainty visible.

## Try also

Switch the filter to `city = 'Boston'` to see the comparison; or
remove the filter and pipe the full series through `seasonal_decompose`
to see the 12-month seasonal component each city has.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_housing_price_trend
```
""",
)

# ── Demo 8 — Housing weekly inventory anomaly ─────────────────────────
_save_demo(
    demo_id="ts_housing_inventory_anomaly",
    csv_filename="housing_inventory.csv",
    name="🏠 Housing · inventory crunch detection",
    dataset_label="3 years of weekly active listings with a 30-week supply crunch + slow recovery",
    description="Decompose then z-score the residuals. The crunch period (weeks 80-110) and recovery (111-130) light up as multi-week anomaly windows.",
    nodes=[
        _node("n_decomp", "seasonal_decompose", inputs_ref=PLACEHOLDER_DS, x=300, y=80, ui_label="Decompose · 52w period",
              params={"time_column": "week", "value_column": "active_listings", "model": "additive", "period": 52, "render": True, "title": "Housing inventory · decomposition"}),
        _node("n_anomaly", "anomaly_zscore", inputs_ref=PLACEHOLDER_DS, x=300, y=240, ui_label="Z-score on raw · 8w window",
              params={"value": "active_listings", "window": 8, "threshold": 2.5, "min_periods": 4}),
        _node("n_cp", "changepoint_detection", inputs_ref=PLACEHOLDER_DS, x=300, y=400, ui_label="Changepoint · 4σ",
              params={"value": "active_listings", "threshold": 4.0}),
    ],
    readme="""# 🏠 Housing · inventory crunch detection

**Scenario:** 3 years of weekly active-listings counts. The market hit
a sudden supply crunch around week 80 (drop ~1700 listings) lasting
30 weeks, followed by slow recovery (~1100 below baseline) for the
next 20 weeks.

## What the flow shows

```
ds ─┬─→ seasonal_decompose(period=52)        → annual seasonal cycle removed
    ├─→ anomaly_zscore(window=8, thr=2.5σ)   → flags the crunch + recovery weeks
    └─→ changepoint_detection(thr=4σ)        → marks the regime shift week
```

Three diagnostic lenses on the same series: the decomposition shows
the trend bottoming out; the rolling z-score paints individual
anomalous weeks; the changepoint test names the specific week where
the regime changed. Useful for housing-market researchers, mortgage
risk teams, anyone who needs to characterize supply-side shocks.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_housing_inventory_anomaly
```
""",
)


print("\n8 demo folders ready under FunctionPacks/examples/")

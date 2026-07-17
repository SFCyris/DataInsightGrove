#!/usr/bin/env python3
"""Generate the 8 time-series demo CSVs in one shot.

Each demo's CSV is intentionally compact (50-300 rows) so the
preview renders fast and the whole story is on screen, but realistic
enough that the resulting charts feel like real-world data —
seasonality, trend, regime shifts, occasional outliers.

Run once from the examples directory:
    cd FunctionPacks/examples/_ts_demos_data
    python3 generate.py
The CSVs land next to this script. The demo folders symlink them in.
"""
from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path


HERE = Path(__file__).resolve().parent
random.seed(42)


def _write(name: str, header: list[str], rows: list[list]) -> None:
    out = HERE / name
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    print(f"  wrote {out.name} · {len(rows)} rows")


# ── Demo 1 — Retail weekly sales (52 weeks × 2 years = 104 weeks) ─────
def gen_retail() -> None:
    rows = []
    base = datetime(2024, 1, 7)  # first Sunday of 2024
    for week in range(104):
        d = base + timedelta(weeks=week)
        # Annual seasonality (peak in Dec) + linear growth + holiday spikes + noise
        seasonal = 250 * math.sin(2 * math.pi * (week % 52) / 52 - math.pi / 2 + 0.3)
        trend = 1000 + week * 4.2
        holiday = 0
        # Black Friday / Christmas weeks
        if (week % 52) in (47, 48, 49, 50, 51):
            holiday = 800 - (51 - (week % 52)) * 130
        noise = random.gauss(0, 60)
        sales = max(200, int(trend + seasonal + holiday + noise))
        rows.append([d.strftime("%Y-%m-%d"), sales])
    _write("retail_sales.csv", ["week", "units_sold"], rows)


# ── Demo 2 — IoT factory sensor (1 reading/min × 8h shift) ────────────
def gen_iot() -> None:
    rows = []
    base = datetime(2026, 3, 4, 6, 0)
    n = 480  # 8 hours @ 1/min
    for i in range(n):
        ts = base + timedelta(minutes=i)
        # Normal vibration: slow rise + noise; 3 anomalous bursts injected
        normal = 0.42 + 0.0003 * i + 0.04 * math.sin(2 * math.pi * i / 60)
        anomaly = 0.0
        if 110 <= i <= 113 or 250 <= i <= 254 or 380 <= i <= 386:
            anomaly = random.uniform(0.6, 1.1)
        v = max(0.0, normal + random.gauss(0, 0.04) + anomaly)
        temp = 67 + random.gauss(0, 0.6) + (3.0 if anomaly > 0 else 0)
        rows.append([ts.strftime("%Y-%m-%d %H:%M:%S"), round(v, 4), round(temp, 2)])
    _write("iot_sensor.csv", ["ts", "vibration_mm_s", "bearing_temp_c"], rows)


# ── Demo 3 — Financial daily returns (2 years) ───────────────────────
def gen_finance() -> None:
    rows = []
    base = datetime(2024, 1, 2)
    price = 152.30
    n = 504  # ~2 trading years
    for i in range(n):
        d = base + timedelta(days=i)
        # Skip weekends
        if d.weekday() >= 5:
            continue
        # Mostly low vol; cluster of high-vol days mid-series
        vol = 0.013
        if 220 <= i <= 280:
            vol = 0.034  # earnings-event-style cluster
        ret = random.gauss(0.0004, vol)
        price *= 1 + ret
        rows.append([d.strftime("%Y-%m-%d"), round(price, 2), round(ret * 100, 4)])
    _write("financial_returns.csv", ["date", "close", "return_pct"], rows)


# ── Demo 4 — Healthcare vitals (continuous monitoring 6 hours) ────────
def gen_vitals() -> None:
    rows = []
    base = datetime(2026, 4, 15, 8, 0)
    # 1 sample every 30s for 6 hours = 720 rows
    for i in range(720):
        ts = base + timedelta(seconds=30 * i)
        hr = 76 + 4 * math.sin(2 * math.pi * i / 100) + random.gauss(0, 1.5)
        spo2 = 97.5 + random.gauss(0, 0.4)
        sbp = 120 + 6 * math.sin(2 * math.pi * i / 220) + random.gauss(0, 2)
        # Two synthetic alert windows: tachycardia + desat
        if 200 <= i <= 230:
            hr += 35  # tachycardia
        if 480 <= i <= 510:
            spo2 -= 5  # desat
            hr += 18
        rows.append([
            ts.strftime("%Y-%m-%d %H:%M:%S"),
            round(hr, 1), round(max(80, spo2), 1), round(sbp, 1),
        ])
    _write("healthcare_vitals.csv", ["ts", "heart_rate_bpm", "spo2_pct", "sbp_mmhg"], rows)


# ── Demo 5 — Hospital readmissions (monthly, 4 years) ────────────────
def gen_readmissions() -> None:
    rows = []
    base = datetime(2022, 1, 31)
    for m in range(48):
        # Monthly: trend down + seasonal (winter higher) + intervention drop at month 30
        baseline = 14.5 - m * 0.04
        seasonal = 1.6 * math.sin(2 * math.pi * (m % 12) / 12 - math.pi)
        intervention = -2.3 if m >= 30 else 0
        rate = baseline + seasonal + intervention + random.gauss(0, 0.4)
        admissions = int(900 + 60 * math.sin(2 * math.pi * m / 12) + random.gauss(0, 25))
        d = base + timedelta(days=30 * m + 30)
        rows.append([d.strftime("%Y-%m-%d"), round(rate, 2), admissions])
    _write("hospital_readmissions.csv", ["month", "readmission_rate_pct", "total_admissions"], rows)


# ── Demo 6 — ER hourly load (28 days, 1 reading/hr) ──────────────────
def gen_er_load() -> None:
    rows = []
    base = datetime(2026, 1, 1, 0, 0)
    for h in range(24 * 28):  # 28 days
        ts = base + timedelta(hours=h)
        hr = h % 24
        dow = (base + timedelta(hours=h)).weekday()
        # Daily pattern: peak 10pm-2am, dip 4am-7am
        daily = 18 - 9 * math.cos(2 * math.pi * (hr - 22) / 24)
        # Weekly pattern: weekends busier evenings
        weekend = 4 if dow in (4, 5) and hr >= 18 else 0
        load = max(2, int(daily + weekend + random.gauss(0, 2.5)))
        rows.append([ts.strftime("%Y-%m-%d %H:%M:%S"), load])
    _write("er_load.csv", ["ts", "patients_admitted"], rows)


# ── Demo 7 — Housing median price (monthly, 5 years, 2 cities) ───────
def gen_housing_price() -> None:
    rows = []
    base = datetime(2021, 1, 1)
    for m in range(60):
        d = base + timedelta(days=30 * m)
        # Two cities: Austin grew fast then plateaued; Boston slow + steady
        austin = 410 + 8.5 * m - 0.08 * m * m + 12 * math.sin(2 * math.pi * (m % 12) / 12)
        boston = 555 + 3.2 * m + 8 * math.sin(2 * math.pi * (m % 12) / 12)
        # Modest noise
        austin += random.gauss(0, 5)
        boston += random.gauss(0, 4)
        rows.append([d.strftime("%Y-%m-%d"), "Austin", round(austin, 1)])
        rows.append([d.strftime("%Y-%m-%d"), "Boston", round(boston, 1)])
    _write("housing_price.csv", ["month", "city", "median_price_kusd"], rows)


# ── Demo 8 — Housing weekly inventory (3 years, sudden supply crunch) ─
def gen_housing_inventory() -> None:
    rows = []
    base = datetime(2023, 1, 8)
    for w in range(156):  # 3 years weekly
        d = base + timedelta(weeks=w)
        # Seasonal: lower inventory in winter
        seasonal = 800 * math.sin(2 * math.pi * ((w % 52) / 52) - math.pi / 2)
        baseline = 5500
        # Sudden supply crunch starting week 80, lasting ~30 weeks
        crunch = -1700 if 80 <= w <= 110 else 0
        # Slow recovery after
        recovery = -1100 if 111 <= w <= 130 else 0
        inv = max(800, int(baseline + seasonal + crunch + recovery + random.gauss(0, 110)))
        rows.append([d.strftime("%Y-%m-%d"), inv])
    _write("housing_inventory.csv", ["week", "active_listings"], rows)


def main() -> None:
    print("Generating 8 time-series demo CSVs:")
    gen_retail()
    gen_iot()
    gen_finance()
    gen_vitals()
    gen_readmissions()
    gen_er_load()
    gen_housing_price()
    gen_housing_inventory()
    print("Done.")


if __name__ == "__main__":
    main()

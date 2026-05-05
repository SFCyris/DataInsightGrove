#!/usr/bin/env python3
"""Generate samples/manufacturing-demo.csv — factory floor sensor telemetry.

Per-machine sensor readings at 5-minute granularity over a 10-day window for
6 production lines (15 machines, 25 rotating operators, ~80 material lots).
Quality outcomes (defect events) are sprinkled with realistic cause-and-effect
windows so a leading-indicator feature ("vibration spike 10 min before defect"
+ "temperature spike 5 min before defect") is discoverable in the data.

The numbers are NOT a real factory readout — they are stylized so a data-prep
demo over them surfaces the right teaching moments:

  - long-form time-series + grouped (line × machine × shift) structure
  - sensor blackouts (5-minute NULL ranges across all sensor cols)
  - 0.5% defect events (rare but not vanishing) with 4 defect_type categories
  - one machine (M-D1) with a slow degradation trend over the 10 days
  - shift-level cycle-time degradation + temperature ramp

Deterministic — seed=42. Re-running produces byte-identical output.

Stdlib only: random / math / csv / datetime. No numpy / scipy / pandas.

Run:
  python samples/_generators/factory_telemetry.py
"""

from __future__ import annotations

import csv
import math
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 42

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "samples" / "manufacturing-demo.csv"

# Target window for the file size — task asks for 2 MB to 5 MB. We aim for
# ~3.5 MB so it's clearly the largest sample but doesn't bloat the repo.
MIN_BYTES = 2 * 1024 * 1024
MAX_BYTES = 5 * 1024 * 1024

# Time window: 10 days at 5-minute granularity = 10 × 24 × 12 = 2,880 ticks
# per machine. Across 15 machines = 43,200 rows. CSV row ≈ 100 chars including
# ts + 14 fields, so we land near ~4 MB which fits the 2-5 MB target. The
# task's original sketch suggested 30 days but the per-row width turned out
# wider than estimated; 10 days is a meaningful window for shift × machine
# rollups, weekend coverage, and the M-D1 degradation trend.
START_TS = datetime(2026, 4, 1, 0, 0, 0)
DAYS = 10
INTERVAL_MIN = 5

# Production layout. Lines A..F, ~15 machines spread non-uniformly so the
# group_aggregate steps in the tutorial reveal differing fleet sizes per line.
MACHINES: list[tuple[str, str]] = [
    ("LINE-A", "M-A1"),
    ("LINE-A", "M-A2"),
    ("LINE-A", "M-A3"),
    ("LINE-B", "M-B1"),
    ("LINE-B", "M-B2"),
    ("LINE-C", "M-C1"),
    ("LINE-C", "M-C2"),
    ("LINE-D", "M-D1"),  # the degrading machine
    ("LINE-D", "M-D2"),
    ("LINE-E", "M-E1"),
    ("LINE-E", "M-E2"),
    ("LINE-E", "M-E3"),
    ("LINE-F", "M-F1"),
    ("LINE-F", "M-F2"),
    ("LINE-F", "M-F3"),
]

# 25 operators rotate across machines + shifts.
OPERATOR_IDS = [f"OP-{i:03d}" for i in range(1, 26)]

# Shifts (8h windows). Shift names + (start_hour, end_hour) inclusive-exclusive.
SHIFTS: list[tuple[str, int, int]] = [
    ("morning",   6, 14),
    ("afternoon", 14, 22),
    ("night",     22, 30),  # 22:00 -> 06:00 (next day) modeled by hour % 24
]

DEFECT_TYPES = ["dimensional", "surface", "assembly", "electrical"]

# ~80 unique material lots across the run, multi-shift batches.
N_MATERIAL_LOTS = 80
LOT_IDS = [f"LOT-{i:04d}" for i in range(1, N_MATERIAL_LOTS + 1)]


# ---------------------------------------------------------------------------
# Helper models
# ---------------------------------------------------------------------------

def shift_for(ts: datetime) -> tuple[str, int]:
    """Return (shift_name, minutes_into_shift) for a given timestamp."""
    h = ts.hour
    if 6 <= h < 14:
        start = ts.replace(hour=6, minute=0, second=0, microsecond=0)
        return "morning", int((ts - start).total_seconds() // 60)
    if 14 <= h < 22:
        start = ts.replace(hour=14, minute=0, second=0, microsecond=0)
        return "afternoon", int((ts - start).total_seconds() // 60)
    # night shift — hour 22-23 today, or 0-5 next day
    if h >= 22:
        start = ts.replace(hour=22, minute=0, second=0, microsecond=0)
    else:
        # past midnight; the night shift began at 22:00 yesterday
        start = (ts - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)
    return "night", int((ts - start).total_seconds() // 60)


def degradation_factor(machine_id: str, day_index: int) -> float:
    """Slow drift for M-D1 over the run; 1.0 (no drift) for everyone else."""
    if machine_id != "M-D1":
        return 1.0
    # Linear degradation: 1.0 at day 0 -> ~1.18 at day 29 (originally tuned
    # for a 30-day window). We keep the same slope so the trend is detectable
    # even on the shorter window — the slope is what's interesting, not the
    # absolute end-state value.
    return 1.0 + 0.006 * day_index


def _stable_hash(*parts: object) -> int:
    """Deterministic hash across Python runs (built-in hash() randomizes its
    seed unless PYTHONHASHSEED is set, so we sum a hand-rolled char rolling
    hash over the str(part) of each input)."""
    acc = 0
    for p in parts:
        for ch in str(p):
            acc = (acc * 131 + ord(ch)) & 0xFFFFFFFF
        acc = (acc * 17) & 0xFFFFFFFF
    return acc


def operator_for(machine_id: str, shift_idx: int, day_index: int, rng: random.Random) -> str:
    """Pick an operator per (machine × shift × day) so the same person stays
    on a machine for the shift but rotates across days."""
    seed_key = _stable_hash(machine_id, shift_idx, day_index)
    return OPERATOR_IDS[seed_key % len(OPERATOR_IDS)]


def material_lot_for(machine_id: str, day_index: int, shift_idx: int) -> str:
    """Material lots span ~3 shifts on a single machine before a fresh batch."""
    bucket = _stable_hash(machine_id, (day_index * 3 + shift_idx) // 3)
    return LOT_IDS[bucket % N_MATERIAL_LOTS]


def fmt_ts(ts: datetime) -> str:
    """ISO-8601 without timezone — DIG's cast_type to datetime handles it."""
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# Defect-event scheduling
# ---------------------------------------------------------------------------

def schedule_defects(rng: random.Random, total_ticks: int) -> dict[tuple[str, int], str]:
    """For each machine, randomly mark ~0.5% of ticks as defect events.

    Returns a dict keyed by (machine_id, tick_index) -> defect_type.
    """
    events: dict[tuple[str, int], str] = {}
    for _, machine_id in MACHINES:
        for tick in range(total_ticks):
            # 0.5% per tick × 8640 ticks ≈ 43 defects per machine ≈ 645 total.
            if rng.random() < 0.005:
                events[(machine_id, tick)] = rng.choice(DEFECT_TYPES)
    return events


def schedule_blackouts(rng: random.Random, total_ticks: int) -> dict[str, set[int]]:
    """5-minute sensor blackouts (one tick range = one blackout). On average
    ~3 blackouts per machine across the 30 days."""
    blackouts: dict[str, set[int]] = {}
    for _, machine_id in MACHINES:
        ticks: set[int] = set()
        n = rng.randint(2, 5)
        for _ in range(n):
            t = rng.randint(0, total_ticks - 1)
            ticks.add(t)
        blackouts[machine_id] = ticks
    return blackouts


# ---------------------------------------------------------------------------
# Per-tick sensor model
# ---------------------------------------------------------------------------

def temperature_c(
    minutes_into_shift: int,
    degr: float,
    is_pre_defect_5min: bool,
    rng: random.Random,
) -> float:
    """Base 65-85°C; ramps up over the shift; spikes to 110+ before defects."""
    # Shift ramp: cold-start 68°C -> stable 78°C around minute 60+; gentle
    # creep up to 84°C late in the shift.
    if minutes_into_shift < 60:
        base = 68.0 + (minutes_into_shift / 60.0) * 8.0  # 68 -> 76
    else:
        base = 76.0 + min(0.0125, (minutes_into_shift - 60) * 0.013) * (minutes_into_shift - 60)
        base = min(base, 85.0)
    base *= degr
    base += rng.gauss(0.0, 1.2)

    if is_pre_defect_5min:
        # Sharp spike: +25-35°C in the 5 minutes before a defect.
        base += rng.uniform(25.0, 35.0)

    return round(base, 2)


def vibration_mm_s(
    minutes_into_shift: int,
    degr: float,
    is_pre_defect_10min: bool,
    rng: random.Random,
) -> float:
    """Baseline 1-3 mm/s RMS; spikes 5-15 mm/s 10 min before defects."""
    base = rng.uniform(1.0, 2.5) * degr
    base += rng.gauss(0.0, 0.15)

    if is_pre_defect_10min:
        # Spike well before the defect — leading indicator.
        base += rng.uniform(4.0, 13.0)

    return round(max(0.0, base), 3)


def pressure_kpa(rng: random.Random) -> float:
    """Hydraulic pressure 200-300 kPa, mostly stable."""
    return round(rng.gauss(250.0, 12.0), 1)


def cycle_time_s(minutes_into_shift: int, degr: float, rng: random.Random) -> float:
    """30-120s; degrades over a shift (operator fatigue) + machine drift."""
    base = 45.0 + (minutes_into_shift / 480.0) * 18.0  # +18s by end of shift
    base *= degr
    base += rng.gauss(0.0, 4.5)
    return round(min(120.0, max(30.0, base)), 2)


# ---------------------------------------------------------------------------
# Main row generator
# ---------------------------------------------------------------------------

def generate_rows(rng: random.Random) -> list[dict[str, object]]:
    total_ticks = DAYS * 24 * (60 // INTERVAL_MIN)  # 30 * 24 * 12 = 8640
    rows: list[dict[str, object]] = []

    defect_events = schedule_defects(rng, total_ticks)
    blackouts = schedule_blackouts(rng, total_ticks)

    # Build a fast lookup: per-machine sets of "pre-defect" tick indexes.
    pre_defect_5min: dict[str, set[int]] = {m: set() for _, m in MACHINES}
    pre_defect_10min: dict[str, set[int]] = {m: set() for _, m in MACHINES}
    for (machine_id, tick), _ in defect_events.items():
        # 1 tick = 5 min, so minus 1 tick = 5 min before, minus 2 = 10 min.
        if tick - 1 >= 0:
            pre_defect_5min[machine_id].add(tick - 1)
        if tick - 2 >= 0:
            pre_defect_10min[machine_id].add(tick - 2)

    # Per-shift counters — reset on shift-change.
    counter_units: dict[str, int] = {m: 0 for _, m in MACHINES}
    counter_defects: dict[str, int] = {m: 0 for _, m in MACHINES}
    counter_kwh: dict[str, float] = {m: 0.0 for _, m in MACHINES}
    last_shift: dict[str, str | None] = {m: None for _, m in MACHINES}

    for tick in range(total_ticks):
        ts = START_TS + timedelta(minutes=tick * INTERVAL_MIN)
        day_index = (ts - START_TS).days
        shift_name, mins_into_shift = shift_for(ts)
        shift_idx = {"morning": 0, "afternoon": 1, "night": 2}[shift_name]

        for line_id, machine_id in MACHINES:
            # Reset per-shift counters at shift change.
            if last_shift[machine_id] != shift_name:
                counter_units[machine_id] = 0
                counter_defects[machine_id] = 0
                counter_kwh[machine_id] = 0.0
                last_shift[machine_id] = shift_name

            degr = degradation_factor(machine_id, day_index)
            blackout = tick in blackouts[machine_id]

            # Base sensor readings (NULL during a blackout).
            if blackout:
                temp = ""
                vib = ""
                pres = ""
                cycle = ""
            else:
                is_pre5 = tick in pre_defect_5min[machine_id]
                is_pre10 = tick in pre_defect_10min[machine_id]
                temp = temperature_c(mins_into_shift, degr, is_pre5, rng)
                vib = vibration_mm_s(mins_into_shift, degr, is_pre10, rng)
                pres = pressure_kpa(rng)
                cycle = cycle_time_s(mins_into_shift, degr, rng)

                # Add a sprinkle of obvious sensor faults — temperature_c spikes
                # to 220°C+ for a single tick (~0.05% of healthy rows). The AI
                # Reviewer should suggest a quality_check expectation.
                if rng.random() < 0.0005:
                    temp = round(220.0 + rng.uniform(0.0, 30.0), 2)

            # Update counters even during blackout (units / energy keep ticking
            # in real plants — the network is just down).
            # Cycle time -> units produced per 5-minute window.
            cycle_for_count = cycle if not blackout else 50.0
            units_this_tick = int(round((INTERVAL_MIN * 60) / float(cycle_for_count)))
            counter_units[machine_id] += units_this_tick
            counter_kwh[machine_id] += round(rng.uniform(0.4, 0.65) * degr, 4)

            is_defect = (machine_id, tick) in defect_events
            defect_type: object = defect_events.get((machine_id, tick), "")
            if is_defect:
                counter_defects[machine_id] += 1

            rows.append({
                "ts": fmt_ts(ts),
                "line_id": line_id,
                "machine_id": machine_id,
                "shift": shift_name,
                "temperature_c": temp,
                "vibration_mm_s": vib,
                "pressure_kpa": pres,
                "cycle_time_s": cycle,
                "units_produced": counter_units[machine_id],
                "defect_count_running": counter_defects[machine_id],
                "is_defect_event": "true" if is_defect else "false",
                "defect_type": defect_type,
                "operator_id": operator_for(machine_id, shift_idx, day_index, rng),
                "material_lot": material_lot_for(machine_id, day_index, shift_idx),
                "power_kwh": round(counter_kwh[machine_id], 3),
            })

    return rows


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "ts",
    "line_id",
    "machine_id",
    "shift",
    "temperature_c",
    "vibration_mm_s",
    "pressure_kpa",
    "cycle_time_s",
    "units_produced",
    "defect_count_running",
    "is_defect_event",
    "defect_type",
    "operator_id",
    "material_lot",
    "power_kwh",
]


def write_csv(rows: list[dict[str, object]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rng = random.Random(SEED)
    rows = generate_rows(rng)
    write_csv(rows, OUT_PATH)
    size = OUT_PATH.stat().st_size

    n_defects = sum(1 for r in rows if r["is_defect_event"] == "true")
    n_blackouts = sum(1 for r in rows if r["temperature_c"] == "")

    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  rows         : {len(rows):,}")
    print(f"  defects      : {n_defects:,}")
    print(f"  blackouts    : {n_blackouts:,}")
    print(f"  output bytes : {size:,}  (≈ {size/1024:.1f} KB / {size/1024/1024:.2f} MB)")

    if not (MIN_BYTES <= size <= MAX_BYTES):
        print(
            f"\nERROR: file size {size:,} bytes is outside the target window "
            f"[{MIN_BYTES:,}, {MAX_BYTES:,}]. Adjust the generator (e.g. tweak "
            f"INTERVAL_MIN or DAYS) and re-run.",
            file=sys.stderr,
        )
        try:
            os.remove(OUT_PATH)
        except OSError:
            pass
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

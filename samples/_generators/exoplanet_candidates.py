#!/usr/bin/env python3
"""
Generate samples/astronomy-demo.csv — synthetic exoplanet-candidate catalog.

Loosely modeled on NASA's Exoplanet Archive shape (Kepler / K2 / TESS), but
all numbers are fabricated. Deterministic with seed=42, stdlib-only
(random / math / csv) so it runs in any DIG checkout without extra deps.

Built-in data-quality wrinkles drive Tutorial 8:
  - 2% NULL transit_duration_hr (truncated light curves)
  - some equilibrium_temp_k = -1 sentinel (pre-cleanup hint)
  - long-period outliers on period_days (single-transit detections)

Run:
    python3 samples/_generators/exoplanet_candidates.py

Output:  samples/astronomy-demo.csv
Target:  ~12k rows, 800 KB - 3 MB
"""

from __future__ import annotations

import csv
import math
import random
import sys
from pathlib import Path

# --- determinism ---------------------------------------------------------
SEED = 42
ROWS = 12_500  # tuned to land safely in the 800 KB - 3 MB band
random.seed(SEED)


# --- distributions -------------------------------------------------------

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lognormal(mu: float, sigma: float) -> float:
    """Draw from a log-normal distribution (stdlib gauss + exp)."""
    return math.exp(random.gauss(mu, sigma))


def truncnorm(mean: float, sigma: float, lo: float, hi: float) -> float:
    """Resample a normal until it lands in [lo, hi]. Bounded loop count
    guards against pathological params."""
    for _ in range(50):
        v = random.gauss(mean, sigma)
        if lo <= v <= hi:
            return v
    return clamp(mean, lo, hi)


def stellar_teff_k() -> int:
    """Effective temperature distribution biased toward G-K dwarfs (~5500 K)
    — roughly the population Kepler/TESS surveys hit. Mixture: 70 % main
    sequence around 5500 K, 20 % cooler M-dwarfs near 3500 K, 10 % hotter
    F stars near 6500 K."""
    bucket = random.random()
    if bucket < 0.70:
        v = random.gauss(5500, 600)
    elif bucket < 0.90:
        v = random.gauss(3500, 350)
    else:
        v = random.gauss(6500, 350)
    return int(clamp(v, 3000, 7500))


def stellar_radius_for_teff(teff: int) -> float:
    """Rough Teff -> radius mapping with scatter. Cooler stars are smaller."""
    if teff < 3800:
        base = 0.55
    elif teff < 5200:
        base = 0.85
    elif teff < 6000:
        base = 1.00
    else:
        base = 1.20
    r = base + random.gauss(0, 0.10)
    return round(clamp(r, 0.4, 1.4), 3)


def period_days() -> float:
    """Log-normal orbital period; occasional very long-period outliers."""
    if random.random() < 0.015:
        # Single-transit candidates with poorly constrained period.
        return round(random.uniform(300, 800), 2)
    p = lognormal(mu=math.log(15), sigma=1.2)
    return round(clamp(p, 0.5, 500), 3)


def transit_depth_ppm(planet_radius_re: float, stellar_radius_rs: float) -> int:
    """Transit depth roughly (R_p / R_*)^2, with measurement scatter."""
    # 1 R_earth ~ 0.00916 R_sun. Convert ratio, square, ppm.
    depth = ((planet_radius_re * 0.00916) / max(stellar_radius_rs, 0.05)) ** 2 * 1_000_000
    depth *= max(0.1, random.gauss(1.0, 0.2))  # measurement noise
    return int(clamp(depth, 50, 50_000))


def transit_duration_hr(period: float, stellar_radius: float) -> float:
    """Roughly proportional to period^(1/3) * stellar_radius, with scatter."""
    base = (period ** (1 / 3)) * stellar_radius * 1.4
    base *= max(0.4, random.gauss(1.0, 0.25))
    return round(clamp(base, 1.0, 15.0), 2)


def equilibrium_temp_k(period: float, teff: int, stellar_radius: float) -> int:
    """T_eq = T_eff * sqrt(R_*/(2 a)) with a ~ period^(2/3). Numerically
    fudged to land in 200-2500 K for the simulated population."""
    a_au = 0.018 * (period ** (2 / 3))  # cheap Kepler-3 stand-in
    a_rs = a_au / max(stellar_radius * 0.00465, 1e-6)  # stellar radii
    teq = teff * math.sqrt(stellar_radius / (2 * max(a_rs, 1.0)))
    teq *= max(0.6, random.gauss(1.0, 0.12))
    return int(clamp(teq, 200, 2500))


def planet_radius_rearth() -> float:
    """Mixture: ~50 % small (sub-Neptune), 30 % Earth-ish, 15 % Neptune-class,
    5 % giants. Matches roughly the Kepler small-planet glut."""
    bucket = random.random()
    if bucket < 0.50:
        v = random.gauss(2.4, 0.7)  # sub-Neptune
    elif bucket < 0.80:
        v = random.gauss(1.1, 0.3)  # Earth-ish
    elif bucket < 0.95:
        v = random.gauss(4.5, 1.5)  # Neptune-ish
    else:
        v = random.gauss(12.0, 4.0)  # giants
    return round(clamp(v, 0.5, 25.0), 2)


def snr_for_depth(depth_ppm: int) -> float:
    """Higher-depth transits get higher SNR on average."""
    base = math.log10(max(depth_ppm, 1)) * 18 - 10
    base += random.gauss(0, 12)
    return round(clamp(base, 5.0, 200.0), 1)


def disposition(snr: float, mission: str) -> str:
    """Joint distribution. Targets roughly 25/55/20
    confirmed/candidate/false_positive across the catalog. Higher SNR bumps
    the chance of a confirmation, low SNR bumps the chance of a false
    positive — but the marginals are pegged to the target population."""
    # Tunable per-bucket probabilities calibrated empirically against the
    # SNR distribution produced by `snr_for_depth` (heavy upper tail).
    if snr < 12:
        # ~5 % of catalog.
        weights = (0.20, 0.20, 0.60)  # confirmed, candidate, false_positive
    elif snr < 25:
        # ~15 % of catalog.
        weights = (0.20, 0.50, 0.30)
    elif snr < 60:
        # ~40 % of catalog.
        weights = (0.25, 0.60, 0.15)
    else:
        # high SNR — most of the catalog. Bias toward candidate so the
        # population marginals come out near 25/55/20.
        weights = (0.27, 0.60, 0.13)
    return random.choices(
        ["confirmed", "candidate", "false_positive"], weights=weights, k=1
    )[0]


def discovery_year(mission: str) -> int:
    """Year ranges by mission: Kepler 2009-2018, K2 2014-2018, TESS 2018-2024."""
    if mission == "Kepler":
        return random.randint(2009, 2018)
    if mission == "K2":
        return random.randint(2014, 2018)
    return random.randint(2018, 2024)


def target_id_for(mission: str) -> str:
    if mission == "Kepler":
        return f"KIC-{random.randint(1_000_000, 12_999_999)}"
    if mission == "K2":
        return f"KIC-{random.randint(200_000_000, 250_999_999)}"
    return f"TIC-{random.randint(10_000_000, 999_999_999)}"


# --- main ---------------------------------------------------------------

COLUMNS = [
    "target_id",
    "mission",
    "ra_deg",
    "dec_deg",
    "stellar_mag",
    "stellar_teff_k",
    "stellar_radius_rsun",
    "period_days",
    "transit_depth_ppm",
    "transit_duration_hr",
    "planet_radius_rearth",
    "equilibrium_temp_k",
    "snr",
    "disposition",
    "discovery_year",
]


def generate_row() -> dict:
    mission = random.choices(
        ["Kepler", "K2", "TESS"], weights=[0.45, 0.10, 0.45], k=1
    )[0]
    teff = stellar_teff_k()
    s_radius = stellar_radius_for_teff(teff)
    period = period_days()
    p_radius = planet_radius_rearth()
    depth = transit_depth_ppm(p_radius, s_radius)
    duration = transit_duration_hr(period, s_radius)
    eq_temp = equilibrium_temp_k(period, teff, s_radius)
    snr = snr_for_depth(depth)
    dispo = disposition(snr, mission)

    # Wrinkle 1: 2% NULL transit_duration_hr (truncated light curves).
    duration_out: str | float = duration
    if random.random() < 0.02:
        duration_out = ""

    # Wrinkle 2: ~3% encode equilibrium_temp_k as -1 sentinel
    # (legacy ETL used -1 instead of NULL — pre-cleanup hint for the tutorial).
    eq_temp_out: int = eq_temp
    if random.random() < 0.03:
        eq_temp_out = -1

    return {
        "target_id": target_id_for(mission),
        "mission": mission,
        "ra_deg": round(random.uniform(0.0, 360.0), 5),
        "dec_deg": round(random.uniform(-90.0, 90.0), 5),
        "stellar_mag": round(clamp(random.gauss(12.0, 2.5), 8.0, 18.0), 2),
        "stellar_teff_k": teff,
        "stellar_radius_rsun": s_radius,
        "period_days": period,
        "transit_depth_ppm": depth,
        "transit_duration_hr": duration_out,
        "planet_radius_rearth": p_radius,
        "equilibrium_temp_k": eq_temp_out,
        "snr": snr,
        "disposition": dispo,
        "discovery_year": discovery_year(mission),
    }


def main() -> int:
    out_path = Path(__file__).resolve().parent.parent / "astronomy-demo.csv"
    rows = [generate_row() for _ in range(ROWS)]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    size = out_path.stat().st_size
    size_kb = size / 1024
    print(f"wrote {out_path} — {len(rows):,} rows, {size_kb:,.1f} KB")

    # Verify file size band — abort if outside [800 KB, 3 MB].
    if size < 800 * 1024:
        print(f"ERROR: file is {size_kb:.1f} KB, below 800 KB target.", file=sys.stderr)
        return 2
    if size > 3 * 1024 * 1024:
        print(f"ERROR: file is {size_kb:.1f} KB, above 3 MB target.", file=sys.stderr)
        return 2

    # Quick sanity report (lets the tutorial reference real numbers).
    n_null_dur = sum(1 for r in rows if r["transit_duration_hr"] == "")
    n_minus_one = sum(1 for r in rows if r["equilibrium_temp_k"] == -1)
    by_dispo: dict[str, int] = {}
    for r in rows:
        by_dispo[r["disposition"]] = by_dispo.get(r["disposition"], 0) + 1
    print(f"  NULL transit_duration_hr: {n_null_dur} ({n_null_dur / ROWS:.1%})")
    print(f"  equilibrium_temp_k=-1:    {n_minus_one} ({n_minus_one / ROWS:.1%})")
    print(f"  disposition mix:          {by_dispo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

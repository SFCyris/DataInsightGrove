#!/usr/bin/env python3
"""Generate samples/aerodynamics-demo.csv — airfoil polar curves.

Writes Cl / Cd / Cm and a few derived columns over a sweep of (airfoil,
Reynolds, alpha) for several NACA profiles. The numbers are NOT a substitute
for XFOIL or wind-tunnel data — they are stylized so that a data-prep tool
demo over them surfaces the right teaching moments (stall onset, L/D peak,
Re-dependence, the laminar bucket on the drag polar).

Deterministic — seed=42. Re-running produces byte-identical output.

Stdlib only: random / math / csv. No numpy / scipy.

After one dry run on 2026-05-03:
  rows         : 17,568
  output bytes : 1,446,242  (≈ 1.38 MB)

Run:
  python samples/_generators/airfoil_polars.py
"""

from __future__ import annotations

import csv
import math
import os
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 42

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "samples" / "aerodynamics-demo.csv"

# Target: between sales-demo (~57 KB) and orders-demo (~695 KB) — task asks
# for 400 KB to 1.5 MB. We aim for ~1.4 MB so the file is meaty enough to
# exercise per-airfoil stall detection but still loads instantly.
MIN_BYTES = 400 * 1024
MAX_BYTES = 1500 * 1024

# 12 NACA profiles. Each carries a rough-tuned base stall angle (deg) and a
# camber-driven Cl-shift. These are deliberately stylized.
AIRFOILS: list[tuple[str, float, float, float]] = [
    # (designation, stall_alpha_deg, cl_offset, cd_min)
    ("NACA-0006",  10.5,  0.00,  0.0055),
    ("NACA-0009",  12.0,  0.00,  0.0060),
    ("NACA-0012",  14.5,  0.00,  0.0065),
    ("NACA-0015",  15.0,  0.00,  0.0072),
    ("NACA-0018",  15.5,  0.00,  0.0085),
    ("NACA-1408",  13.5,  0.10,  0.0062),
    ("NACA-2412",  15.0,  0.20,  0.0067),
    ("NACA-2415",  15.5,  0.20,  0.0075),
    ("NACA-4412",  16.0,  0.40,  0.0070),
    ("NACA-4415",  16.5,  0.40,  0.0078),
    ("NACA-23012", 17.0,  0.30,  0.0068),
    ("NACA-63-215", 16.0, 0.25,  0.0064),
]

REYNOLDS: list[float] = [5e4, 1e5, 2e5, 5e5, 1e6, 3e6]

ALPHA_MIN = -10.0
ALPHA_MAX = 20.0
ALPHA_STEP = 0.5

# Each (airfoil, Re, alpha) point is sampled this many times — simulating
# multiple wind-tunnel passes (with measurement noise) instead of a single
# clean curve. Adds a real-world wrinkle: when users group by airfoil they
# need to think about whether to mean / median across replicates.
RUNS_PER_POINT = 4


# ---------------------------------------------------------------------------
# Aerodynamics models (intentionally simple but qualitatively right)
# ---------------------------------------------------------------------------

def re_stall_shift(reynolds: float) -> float:
    """Higher Re delays stall slightly. Capped so the change is gentle."""
    # log10(Re/2e5) gives ~0 at the mid-range, ±1 at the extremes.
    delta = 1.5 * math.log10(reynolds / 2e5)
    return max(-3.0, min(3.0, delta))


def cl_curve(alpha_deg: float, stall_alpha: float, cl_offset: float) -> tuple[float, bool]:
    """Piecewise lift-coefficient model.

    Below stall: ~2π linear (in radians) with the camber offset baked in.
    Above stall: post-stall Cl drops ~30% and decays softly.

    Returns (cl, stalled).
    """
    alpha_rad = math.radians(alpha_deg)
    stall_rad = math.radians(stall_alpha)

    # Linear region: Cl = 2π·α + cl_offset   (thin-airfoil baseline)
    cl_linear = 2.0 * math.pi * alpha_rad + cl_offset

    if alpha_deg <= stall_alpha:
        return cl_linear, False

    # Post-stall: drop and gradual decay
    cl_at_stall = 2.0 * math.pi * stall_rad + cl_offset
    over = alpha_deg - stall_alpha
    decay = math.exp(-over / 8.0)            # decays toward zero
    cl_post = cl_at_stall * 0.70 * decay     # 30% loss, then softens
    return cl_post, True


def cd_curve(alpha_deg: float, stall_alpha: float, cd_min: float, reynolds: float) -> float:
    """Drag coefficient model.

    - Quadratic-ish in alpha around the laminar bucket (zero-lift drag).
    - Re-dependence: lower Re -> higher Cd (boundary-layer transition).
    - Sharp rise after stall.
    """
    # Re scaling: Cd0 grows ~ Re^-0.2 around 1e5
    re_scale = (1e5 / reynolds) ** 0.2
    cd0 = cd_min * re_scale

    # Bucket near alpha=2° (typical laminar minimum for cambered foils)
    alpha_rel = alpha_deg - 2.0
    cd = cd0 + 0.0015 * (alpha_rel ** 2)

    if alpha_deg > stall_alpha:
        over = alpha_deg - stall_alpha
        cd += 0.02 * over + 0.005 * (over ** 1.5)

    return cd


def cm_curve(alpha_deg: float, cl_offset: float) -> float:
    """Pitching moment — small, mostly negative for cambered foils."""
    base = -0.05 - 0.5 * cl_offset
    drift = -0.001 * alpha_deg
    return base + drift


def transition_point(alpha_deg: float, reynolds: float) -> float:
    """Boundary-layer transition point as a fraction of chord [0..1].

    High Re or high alpha drives transition forward (toward leading edge);
    low Re / low alpha leaves laminar flow attached further back.
    """
    re_term = max(0.05, 1.0 - 0.18 * math.log10(reynolds / 5e4))
    alpha_term = max(0.0, 0.6 - 0.025 * abs(alpha_deg))
    pt = (re_term * 0.7) + (alpha_term * 0.3)
    return max(0.02, min(0.98, pt))


def flow_regime(reynolds: float, alpha_deg: float, stalled: bool) -> str:
    """Categorical regime label."""
    if stalled:
        return "turbulent"
    if reynolds < 1e5:
        return "laminar"
    if reynolds < 5e5:
        return "transitional"
    return "turbulent"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_rows(rng: random.Random) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    n_steps = int(round((ALPHA_MAX - ALPHA_MIN) / ALPHA_STEP)) + 1
    for designation, base_stall, cl_offset, cd_min in AIRFOILS:
        for re_val in REYNOLDS:
            stall_alpha = base_stall + re_stall_shift(re_val)
            for i in range(n_steps):
                alpha = ALPHA_MIN + i * ALPHA_STEP

                cl_clean, stalled = cl_curve(alpha, stall_alpha, cl_offset)
                cd_clean = cd_curve(alpha, stall_alpha, cd_min, re_val)
                cm_val = cm_curve(alpha, cl_offset)

                for run_idx in range(1, RUNS_PER_POINT + 1):
                    # Add measurement noise — small, alpha-dependent.
                    cl = cl_clean + rng.gauss(0.0, 0.012)
                    cd = cd_clean + rng.gauss(0.0, 0.0009)
                    # Some cd values can dip just below the noise threshold so
                    # the tutorial can show an expectations 'cd > 0' assertion.
                    if rng.random() < 0.012:
                        cd = max(0.00005, cd_clean - abs(rng.gauss(0.0008, 0.0003)))

                    # cl/cd ratio (skip when cd is essentially zero)
                    cl_cd_ratio = cl / cd if abs(cd) > 1e-6 else 0.0

                    tp = transition_point(alpha, re_val)
                    # 1.5% missing transition_pt_chord — the wind-tunnel sensor
                    # drops out under specific high-alpha turbulent conditions.
                    if rng.random() < 0.015:
                        tp_out: object = ""  # NULL on CSV write
                    else:
                        tp_out = round(tp, 4)

                    rows.append({
                        "airfoil":              designation,
                        "reynolds":             int(re_val),
                        "alpha_deg":            round(alpha, 2),
                        "run_id":               f"run_{run_idx:02d}",
                        "cl":                   round(cl, 4),
                        "cd":                   round(cd, 5),
                        "cm":                   round(cm_val, 4),
                        "cl_cd_ratio":          round(cl_cd_ratio, 3),
                        "flow_regime":          flow_regime(re_val, alpha, stalled),
                        "stalled":              "true" if stalled else "false",
                        "transition_pt_chord":  tp_out,
                    })
    return rows


def write_csv(rows: list[dict[str, object]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "airfoil",
        "reynolds",
        "alpha_deg",
        "run_id",
        "cl",
        "cd",
        "cm",
        "cl_cd_ratio",
        "flow_regime",
        "stalled",
        "transition_pt_chord",
    ]
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rng = random.Random(SEED)
    rows = generate_rows(rng)
    write_csv(rows, OUT_PATH)
    size = OUT_PATH.stat().st_size
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  rows         : {len(rows):,}")
    print(f"  output bytes : {size:,}  (≈ {size/1024:.1f} KB / {size/1024/1024:.2f} MB)")
    if not (MIN_BYTES <= size <= MAX_BYTES):
        print(
            f"\nERROR: file size {size:,} bytes is outside the target window "
            f"[{MIN_BYTES:,}, {MAX_BYTES:,}]. Adjust the generator (e.g. tweak "
            f"ALPHA_STEP or the Reynolds list) and re-run.",
            file=sys.stderr,
        )
        # Remove the bad file so re-runs don't cache it.
        try:
            os.remove(OUT_PATH)
        except OSError:
            pass
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

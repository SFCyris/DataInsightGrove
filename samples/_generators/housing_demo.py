#!/usr/bin/env python3
"""Generate the housing demo: 4 interrelated CSVs with US-style real-estate
data including geographical coordinates so the demo pipeline can render a
proper map output.

Tables:
  - housing-listings-demo.csv  (≈ 5,000 rows × 12 cols, includes lat/lon)
  - housing-sales-demo.csv     (≈ 4,500 rows × 7 cols)
  - housing-schools-demo.csv   (≈ 1,200 rows × 7 cols, includes lat/lon)
  - housing-incidents-demo.csv (≈ 6,000 rows × 6 cols, includes lat/lon)

Geographic coverage spans 8 metro areas across the continental US so the
final map output shows recognizable city clusters rather than a uniform
sprinkle. Each metro center has a hand-picked (lat, lon) and listings spread
within ~25 km radius.

Deterministic — seed = 42. Stdlib only.

Run:
  python samples/_generators/housing_demo.py
"""

from __future__ import annotations

import csv
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "samples"

START_DATE = datetime(2024, 5, 1)
END_DATE = datetime(2026, 5, 1)

N_LISTINGS = 5_000
N_SALES = 4_500
N_SCHOOLS = 1_200
N_INCIDENTS = 6_000

# 8 metro areas: (city, state, center_lat, center_lon, weight, price_mult).
# `weight` controls how many listings drop in this metro; `price_mult` is the
# market multiplier on the base price model (Bay Area + NYC are pricier).
METROS = [
    ("San Francisco", "CA", 37.7749, -122.4194, 0.18, 2.10),
    ("Los Angeles",   "CA", 34.0522, -118.2437, 0.20, 1.55),
    ("Seattle",       "WA", 47.6062, -122.3321, 0.10, 1.45),
    ("Denver",        "CO", 39.7392, -104.9903, 0.08, 1.10),
    ("Chicago",       "IL", 41.8781,  -87.6298, 0.10, 0.95),
    ("Austin",        "TX", 30.2672,  -97.7431, 0.10, 1.05),
    ("Miami",         "FL", 25.7617,  -80.1918, 0.10, 1.30),
    ("New York",      "NY", 40.7128,  -74.0060, 0.14, 1.85),
]

PROPERTY_TYPES = ["single-family", "condo", "townhouse", "multi-family"]
PROPERTY_TYPE_WEIGHTS = [0.55, 0.28, 0.12, 0.05]

LIST_STATUSES = ["active", "pending", "sold", "withdrawn", "expired"]
LIST_STATUS_WEIGHTS = [0.30, 0.10, 0.50, 0.05, 0.05]

SCHOOL_TYPES = ["elementary", "middle", "high", "K-12", "charter"]
SCHOOL_TYPE_WEIGHTS = [0.45, 0.20, 0.20, 0.05, 0.10]

CRIME_TYPES = [
    "burglary", "theft-from-vehicle", "vandalism", "assault",
    "drug-violation", "robbery", "vehicle-theft", "fraud", "other",
]
CRIME_TYPE_WEIGHTS = [0.18, 0.22, 0.13, 0.10, 0.09, 0.05, 0.08, 0.07, 0.08]

# Street name pieces — combined into "123 Maple St" style addresses.
STREET_NAMES = [
    "Maple", "Oak", "Pine", "Cedar", "Birch", "Elm", "Walnut",
    "Hill", "Ridge", "Valley", "Park", "Lake", "River", "Forest",
    "Sunset", "Sunrise", "Madison", "Jefferson", "Lincoln", "Washington",
    "Mission", "Market", "Spring", "Summer", "Winter", "Autumn",
]
STREET_TYPES = ["St", "Ave", "Blvd", "Dr", "Ln", "Way", "Ct", "Pl"]


def weighted_choice(rng: random.Random, items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def random_dt(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, span))


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def jitter_latlon(rng: random.Random, lat: float, lon: float, max_km: float = 25.0) -> tuple[float, float]:
    """Return a (lat, lon) randomly offset from the center, within ~max_km.

    1° of latitude ≈ 111 km. 1° of longitude varies with cos(lat). We sample
    a uniform radius (skewed to outer rings — sqrt for uniform-area) and a
    random angle so the result is reasonably "uniform on disk" rather than
    "uniform on rectangle".
    """
    r = max_km * math.sqrt(rng.random())   # km
    theta = rng.uniform(0, 2 * math.pi)
    dlat = (r * math.cos(theta)) / 111.0
    dlon = (r * math.sin(theta)) / (111.0 * math.cos(math.radians(lat)))
    return (round(lat + dlat, 6), round(lon + dlon, 6))


def random_address(rng: random.Random) -> str:
    n = rng.randint(10, 9999)
    name = rng.choice(STREET_NAMES)
    typ = rng.choice(STREET_TYPES)
    return f"{n} {name} {typ}"


# ---- listings ----------------------------------------------------------

def gen_listings(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    metro_weights = [m[4] for m in METROS]
    metro_indexes = list(range(len(METROS)))
    for i in range(N_LISTINGS):
        lid = f"LIST-{i+1:06d}"
        metro_idx = rng.choices(metro_indexes, weights=metro_weights, k=1)[0]
        city, state, c_lat, c_lon, _, price_mult = METROS[metro_idx]
        lat, lon = jitter_latlon(rng, c_lat, c_lon, max_km=25.0)
        ptype = weighted_choice(rng, PROPERTY_TYPES, PROPERTY_TYPE_WEIGHTS)
        # Beds + baths + sqft by type.
        if ptype == "condo":
            beds = rng.randint(0, 3)
            baths = max(1, beds + (1 if rng.random() < 0.4 else 0))
            sqft = int(max(450, rng.gauss(1100, 300)))
        elif ptype == "townhouse":
            beds = rng.randint(2, 4)
            baths = beds - rng.randint(0, 1)
            sqft = int(max(900, rng.gauss(1700, 400)))
        elif ptype == "multi-family":
            beds = rng.randint(4, 8)
            baths = max(2, beds - rng.randint(0, 2))
            sqft = int(max(1500, rng.gauss(3200, 800)))
        else:  # single-family
            beds = rng.randint(2, 6)
            baths = max(1, beds - rng.randint(0, 1))
            sqft = int(max(800, rng.gauss(2100, 600)))
        year_built = rng.randint(1900, 2025)
        # Base price model: ~$300/sqft × multiplier × age penalty.
        age_penalty = max(0.6, 1.0 - (2025 - year_built) * 0.0030)
        list_price = int(sqft * 300 * price_mult * age_penalty * rng.uniform(0.78, 1.25))
        # Snap to nearest $5k.
        list_price = (list_price // 5000) * 5000
        list_status = weighted_choice(rng, LIST_STATUSES, LIST_STATUS_WEIGHTS)
        listed_at = random_dt(rng, START_DATE, END_DATE)
        zipc = f"{rng.randint(10000, 99999)}"
        # 0.5% have null lat (data quality teaching moment).
        if rng.random() < 0.005:
            lat_out = ""
            lon_out = ""
        else:
            lat_out = lat
            lon_out = lon
        rows.append({
            "listing_id": lid,
            "address": random_address(rng),
            "city": city,
            "state": state,
            "zip_code": zipc,
            "latitude": lat_out,
            "longitude": lon_out,
            "property_type": ptype,
            "beds": beds,
            "baths": baths,
            "sqft": sqft,
            "year_built": year_built,
            "list_price_usd": list_price,
            "list_status": list_status,
            "listed_at": fmt_date(listed_at),
        })
    return rows


# ---- sales -------------------------------------------------------------

def gen_sales(rng: random.Random, listings: list[dict]) -> list[dict]:
    rows: list[dict] = []
    sold = [l for l in listings if l["list_status"] == "sold"]
    rng.shuffle(sold)
    n = min(N_SALES, len(sold))
    for i in range(n):
        lst = sold[i]
        sid = f"SALE-{i+1:06d}"
        listed_at = datetime.fromisoformat(lst["listed_at"] + "T00:00:00")
        days_on_market = max(1, int(rng.gauss(45, 25)))
        sale_dt = listed_at + timedelta(days=days_on_market)
        if sale_dt > END_DATE:
            sale_dt = END_DATE - timedelta(days=rng.randint(1, 7))
        # Sale price slightly above or below list (8% std).
        sale_price = int(lst["list_price_usd"] * rng.uniform(0.92, 1.08))
        sale_price = (sale_price // 1000) * 1000
        agent_id = f"AGT-{rng.randint(1, 800):04d}"
        rows.append({
            "sale_id": sid,
            "listing_id": lst["listing_id"],
            "sale_date": fmt_date(sale_dt),
            "sale_price_usd": sale_price,
            "days_on_market": days_on_market,
            "agent_id": agent_id,
            "financing": rng.choices(
                ["conventional", "fha", "va", "cash", "other"],
                weights=[0.55, 0.20, 0.05, 0.18, 0.02], k=1,
            )[0],
        })
    return rows


# ---- schools -----------------------------------------------------------

def gen_schools(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    metro_weights = [m[4] for m in METROS]
    metro_indexes = list(range(len(METROS)))
    for i in range(N_SCHOOLS):
        sid = f"SCH-{i+1:05d}"
        metro_idx = rng.choices(metro_indexes, weights=metro_weights, k=1)[0]
        city, state, c_lat, c_lon, _, _ = METROS[metro_idx]
        lat, lon = jitter_latlon(rng, c_lat, c_lon, max_km=30.0)
        stype = weighted_choice(rng, SCHOOL_TYPES, SCHOOL_TYPE_WEIGHTS)
        # Rating 1-10, biased high.
        rating = max(1, min(10, int(round(rng.gauss(7.2, 1.5)))))
        enrollment = int(max(60, rng.gauss(550, 220)))
        rows.append({
            "school_id": sid,
            "school_name": f"{rng.choice(STREET_NAMES)} {stype.title()} School",
            "city": city,
            "state": state,
            "school_type": stype,
            "rating_1_10": rating,
            "enrollment": enrollment,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
        })
    return rows


# ---- incidents ---------------------------------------------------------

def gen_incidents(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    metro_weights = [m[4] for m in METROS]
    metro_indexes = list(range(len(METROS)))
    for i in range(N_INCIDENTS):
        iid = f"INC-{i+1:06d}"
        metro_idx = rng.choices(metro_indexes, weights=metro_weights, k=1)[0]
        _, _, c_lat, c_lon, _, _ = METROS[metro_idx]
        lat, lon = jitter_latlon(rng, c_lat, c_lon, max_km=20.0)
        ctype = weighted_choice(rng, CRIME_TYPES, CRIME_TYPE_WEIGHTS)
        ts = random_dt(rng, START_DATE, END_DATE)
        severity = rng.choices(["low", "medium", "high"], weights=[0.55, 0.35, 0.10], k=1)[0]
        rows.append({
            "incident_id": iid,
            "occurred_at": fmt_dt(ts),
            "incident_type": ctype,
            "severity": severity,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
        })
    return rows


# ---- writer ------------------------------------------------------------

def write_csv(rows: list[dict], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rng = random.Random(SEED)
    listings = gen_listings(rng)
    sales = gen_sales(rng, listings)
    schools = gen_schools(rng)
    incidents = gen_incidents(rng)

    targets = [
        (listings, "housing-listings-demo.csv",
         ["listing_id", "address", "city", "state", "zip_code",
          "latitude", "longitude", "property_type", "beds", "baths",
          "sqft", "year_built", "list_price_usd", "list_status", "listed_at"]),
        (sales, "housing-sales-demo.csv",
         ["sale_id", "listing_id", "sale_date", "sale_price_usd",
          "days_on_market", "agent_id", "financing"]),
        (schools, "housing-schools-demo.csv",
         ["school_id", "school_name", "city", "state", "school_type",
          "rating_1_10", "enrollment", "latitude", "longitude"]),
        (incidents, "housing-incidents-demo.csv",
         ["incident_id", "occurred_at", "incident_type", "severity",
          "latitude", "longitude"]),
    ]

    for rows, fname, fields in targets:
        path = OUT_DIR / fname
        write_csv(rows, path, fields)
        size = path.stat().st_size
        print(f"wrote {path.relative_to(REPO_ROOT)}: {len(rows):,} rows × {len(fields)} cols ({size/1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

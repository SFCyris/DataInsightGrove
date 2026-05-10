"""Generator for samples/economy-demo.csv — monthly macroeconomic indicators per country.

Determinism: seed=42, only stdlib (random, math, csv). Re-runs produce identical output.

Domain: 50 representative economies × monthly observations from 2000-01 to 2025-12.
Real-world wrinkles included on purpose so the AI Pipeline Reviewer earns its keep:

  * 1% NULL unemployment_rate (some country-months don't report)
  * CHN policy_rate is NULL pre-2015 (managed-rate era — "data quality varies by source")
  * VEN / ARG inflation_cpi_yoy occasionally hits 100+ (hyperinflation episodes)
  * 2008 + 2020 GDP shock dips
  * 2022-23 inflation spike across the board
  * Slow population growth, currency crashes for fragile-currency countries

Run from repo root:
    python samples/_generators/macro_indicators.py
"""

from __future__ import annotations

import csv
import math
import os
import random

SEED = 42
START_YEAR = 2000
END_YEAR = 2025  # inclusive
OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "economy-demo.csv",
)

# (iso3, display_name, region, gdp_baseline_bn_2000, fx_baseline,
#  inflation_baseline_pct, unemployment_baseline_pct, debt_baseline_pct,
#  population_millions_2000, is_advanced)
COUNTRIES: list[tuple[str, str, str, float, float, float, float, float, float, bool]] = [
    # North America
    ("USA", "United States",          "North America", 10250.0,    1.00,  2.5,  4.0,   55.0, 282.0, True),
    ("CAN", "Canada",                 "North America",   744.0,    1.49,  2.3,  6.8,   80.0,  31.0, True),
    ("MEX", "Mexico",                 "North America",   707.0,    9.46,  4.5,  3.5,   40.0, 102.0, False),
    # Europe
    ("DEU", "Germany",                "Europe",         1950.0,    1.07,  1.6,  7.8,   60.0,  82.4, True),
    ("FRA", "France",                 "Europe",         1370.0,    1.07,  1.7,  9.0,   58.0,  60.9, True),
    ("GBR", "United Kingdom",         "Europe",         1660.0,    0.66,  1.5,  5.4,   40.0,  58.9, True),
    ("ITA", "Italy",                  "Europe",         1140.0,    1.07,  2.4,  10.0, 105.0,  56.9, True),
    ("ESP", "Spain",                  "Europe",          600.0,    1.07,  3.2,  11.5,  58.0,  40.5, True),
    ("NLD", "Netherlands",            "Europe",          417.0,    1.07,  2.0,  3.5,   54.0,  15.9, True),
    ("BEL", "Belgium",                "Europe",          238.0,    1.07,  1.9,  7.0,  108.0,  10.3, True),
    ("CHE", "Switzerland",            "Europe",          273.0,    1.69,  1.0,  2.5,   55.0,   7.2, True),
    ("SWE", "Sweden",                 "Europe",          261.0,    8.93,  1.5,  6.5,   55.0,   8.9, True),
    ("NOR", "Norway",                 "Europe",          172.0,    8.81,  2.5,  3.2,   30.0,   4.5, True),
    ("DNK", "Denmark",                "Europe",          164.0,    8.07,  2.3,  4.5,   50.0,   5.3, True),
    ("FIN", "Finland",                "Europe",          126.0,    1.07,  1.5,  9.5,   42.0,   5.2, True),
    ("AUT", "Austria",                "Europe",          197.0,    1.07,  1.7,  4.5,   65.0,   8.0, True),
    ("IRL", "Ireland",                "Europe",          100.0,    1.07,  3.0,  4.5,   30.0,   3.8, True),
    ("POL", "Poland",                 "Europe",          172.0,    4.10,  4.5,  16.0,  37.0,  38.6, False),
    ("CZE", "Czech Republic",         "Europe",           62.0,   38.59,  3.5,  8.5,   18.0,  10.3, False),
    ("HUN", "Hungary",                "Europe",           48.0,  282.18,  6.0,  6.5,   55.0,  10.2, False),
    ("ROU", "Romania",                "Europe",           38.0,    2.93, 22.0,  7.0,   20.0,  22.4, False),
    ("PRT", "Portugal",               "Europe",          120.0,    1.07,  2.8,  4.5,   55.0,  10.3, True),
    ("GRC", "Greece",                 "Europe",          135.0,    1.07,  3.2,  11.5,  100.0, 10.9, True),
    ("RUS", "Russia",                 "Europe",          260.0,   28.13, 20.5,  10.6,  60.0, 146.6, False),
    ("UKR", "Ukraine",                "Europe",           33.0,    5.44, 28.0,  11.6,  45.0,  49.2, False),
    ("TUR", "Turkey",                 "Europe",          273.0,    0.62, 55.0,   6.5,  56.0,  64.3, False),
    # Asia-Pacific
    ("JPN", "Japan",                  "Asia-Pacific",   4731.0,  108.00, -0.5,  4.7,  130.0, 126.8, True),
    ("CHN", "China",                  "Asia-Pacific",   1211.0,    8.28,  0.5,  3.1,   20.0, 1262.6, False),
    ("KOR", "South Korea",            "Asia-Pacific",    562.0, 1131.16,  2.3,  4.4,   17.0,  47.4, True),
    ("IND", "India",                  "Asia-Pacific",    468.0,   44.94,  4.0,  4.3,   72.0, 1057.0, False),
    ("IDN", "Indonesia",              "Asia-Pacific",    165.0, 8421.78,  3.7,  6.1,   95.0, 211.5, False),
    ("AUS", "Australia",              "Asia-Pacific",    415.0,    1.72,  4.5,  6.3,   20.0,  19.2, True),
    ("NZL", "New Zealand",            "Asia-Pacific",     53.0,    2.20,  2.7,  6.2,   33.0,   3.9, True),
    ("THA", "Thailand",               "Asia-Pacific",    127.0,   40.11,  1.6,  2.4,   58.0,  62.4, False),
    ("MYS", "Malaysia",               "Asia-Pacific",     94.0,    3.80,  1.5,  3.0,   42.0,  23.4, False),
    ("PHL", "Philippines",            "Asia-Pacific",     82.0,   44.19,  4.5,  10.1,  68.0,  77.9, False),
    ("VNM", "Vietnam",                "Asia-Pacific",     33.0,14167.75, -1.7,  2.3,   42.0,  79.0, False),
    ("SGP", "Singapore",              "Asia-Pacific",     96.0,    1.72,  1.4,  2.7,   85.0,   4.0, True),
    ("PAK", "Pakistan",               "Asia-Pacific",     74.0,   53.65,  4.4,  6.0,   78.0, 142.3, False),
    # Latin America
    ("BRA", "Brazil",                 "Latin America",   656.0,    1.83,  7.0,  9.6,   65.0, 175.3, False),
    ("ARG", "Argentina",              "Latin America",   284.0,    1.00, 25.0,  15.0,  45.0,  37.1, False),
    ("CHL", "Chile",                  "Latin America",    77.0,  535.47,  4.5,  9.7,   13.0,  15.4, False),
    ("COL", "Colombia",               "Latin America",   100.0, 2087.42,  9.5,  17.5,  35.0,  39.7, False),
    ("PER", "Peru",                   "Latin America",    53.0,    3.49,  3.7,  7.4,   45.0,  26.0, False),
    ("VEN", "Venezuela",              "Latin America",   117.0,  679.40, 16.0,  14.0,  29.0,  24.3, False),
    # Africa
    ("ZAF", "South Africa",           "Africa",          136.0,    6.94,  5.3,  23.0,  43.0,  44.0, False),
    ("EGY", "Egypt",                  "Africa",          100.0,    3.47,  2.7,  9.0,   90.0,  68.8, False),
    ("NGA", "Nigeria",                "Africa",           46.0,  101.70,  6.9,  13.6,  84.0, 122.4, False),
    ("KEN", "Kenya",                  "Africa",           13.0,   76.18, 10.0,  10.0,  53.0,  31.4, False),
    # Middle East
    ("SAU", "Saudi Arabia",           "Middle East",     189.0,    3.75, -1.1,  4.6,   95.0,  21.1, False),
    ("ISR", "Israel",                 "Middle East",     133.0,    4.08,  1.1,  8.8,   80.0,   6.3, True),
    ("ARE", "United Arab Emirates",   "Middle East",      96.0,    3.67,  1.4,  2.4,   12.0,   3.1, True),
]

assert 50 <= len(COUNTRIES) <= 55, f"Expected ~50 countries, got {len(COUNTRIES)}"

# Months from START_YEAR-01 to END_YEAR-12 inclusive
def month_iter() -> list[tuple[int, int]]:
    return [(y, m) for y in range(START_YEAR, END_YEAR + 1) for m in range(1, 13)]


def crisis_factor(year: int, month: int) -> float:
    """Multiplicative shock to GDP growth around 2008-2009 and 2020-2021."""
    # 2008 GFC: dip Q4 2008 - Q4 2009
    if (year == 2008 and month >= 9) or year == 2009:
        return -0.04 + (random.random() - 0.5) * 0.01  # ~-4% drag
    # 2020 COVID: very deep but short
    if year == 2020 and 3 <= month <= 9:
        return -0.10 + (random.random() - 0.5) * 0.02  # ~-10% drag
    if year == 2020 and month >= 10:
        return -0.04
    if year == 2021 and month <= 6:
        return 0.05  # rebound
    return 0.0


def inflation_regime(year: int) -> float:
    """Global inflation backdrop — 2022-23 spike, otherwise mild."""
    if year == 2022:
        return 5.5
    if year == 2023:
        return 3.2
    if year == 2024:
        return 1.0
    if year >= 2010 and year <= 2019:
        return -0.4  # disinflation decade
    return 0.0


def policy_rate_regime(year: int, baseline: float) -> float:
    """Global policy-rate backdrop — near-zero post-2008, hike from 2022."""
    if year < 2008:
        return baseline
    if year < 2015:
        return max(0.0, baseline - 3.5)  # ZIRP era
    if year < 2022:
        return max(0.0, baseline - 2.0)
    if year == 2022:
        return baseline + 1.5
    if year >= 2023:
        return baseline + 2.5
    return baseline


def fx_drift(year: int, country_iso: str, baseline_fx: float) -> float:
    """Country-specific FX drift. Fragile currencies depreciate steadily."""
    years_in = year - START_YEAR
    if country_iso == "USA":
        return 1.0
    if country_iso == "VEN":
        # Bolivar collapse — exponential depreciation post-2013
        if year < 2013:
            return baseline_fx * (1.0 + 0.05 * years_in)
        return baseline_fx * (10.0 ** ((year - 2012) * 0.4))
    if country_iso == "ARG":
        if year < 2018:
            return baseline_fx * (1.0 + 0.12 * years_in)
        return baseline_fx * (1.5 ** (year - 2017))
    if country_iso == "TUR":
        return baseline_fx * (0.85 ** years_in)  # lira depreciates
    if country_iso == "RUS":
        if year < 2014:
            return baseline_fx * (1.0 - 0.005 * years_in)
        return baseline_fx * (1.0 + 0.06 * (year - 2013))
    if country_iso in ("BRA", "COL", "MXN"):
        return baseline_fx * (1.0 + 0.015 * years_in)
    if country_iso in ("DEU", "FRA", "ITA", "ESP", "NLD", "BEL", "AUT", "IRL", "PRT", "GRC", "FIN"):
        # Euro members — drift modestly vs USD
        return baseline_fx * (0.92 + 0.01 * math.sin(years_in / 3))
    # Default: mean-reverting drift
    return baseline_fx * (1.0 + 0.005 * math.sin(years_in / 4))


def hyperinflation_kick(country_iso: str, year: int, base_inflation: float) -> float:
    if country_iso == "VEN" and year >= 2014:
        # Hyperinflation episode
        if year >= 2017 and year <= 2020:
            return 250.0 + random.uniform(-50, 100)
        return 50.0 + random.uniform(-10, 40)
    if country_iso == "ARG":
        if year >= 2023:
            return 110.0 + random.uniform(-20, 80)  # 2023-24 hyperinflation
        if year >= 2022:
            return 70.0 + random.uniform(-15, 35)
        if year >= 2018:
            return 40.0 + random.uniform(-10, 20)
    if country_iso == "TUR" and year >= 2022:
        return 55.0 + random.uniform(-10, 20)
    if country_iso == "ZWE":
        return 200.0  # not in our list but kept for symmetry
    return base_inflation


def main() -> None:
    random.seed(SEED)
    rows: list[dict] = []
    months = month_iter()

    for (iso, name, region, gdp_base, fx_base, inf_base, unemp_base,
         debt_base, pop_base, advanced) in COUNTRIES:

        gdp = gdp_base
        debt_pct = debt_base
        pop = pop_base
        prev_year_gdp_by_month: dict[int, float] = {}

        for idx, (year, month) in enumerate(months):
            # GDP: nominal baseline + 2-3% annual growth + monthly noise + crisis dips
            country_growth_per_month = (0.0021 if advanced else 0.0035) + random.gauss(0, 0.0015)
            crisis = crisis_factor(year, month)
            month_growth = country_growth_per_month + crisis / 12.0
            gdp = gdp * (1.0 + month_growth)
            # Hyperinflation distorts nominal GDP for VEN/ARG/TUR
            if iso == "VEN" and year >= 2017:
                gdp = gdp * (1.0 + 0.2)
            if iso == "ARG" and year >= 2022:
                gdp = gdp * (1.0 + 0.05)

            # YoY growth — compare to same-month-last-year if we have it
            prev_gdp = prev_year_gdp_by_month.get(month)
            prev_year_gdp_by_month[month] = gdp
            if prev_gdp:
                gdp_growth_yoy = (gdp / prev_gdp - 1.0) * 100.0
            else:
                gdp_growth_yoy = country_growth_per_month * 12.0 * 100.0

            # Inflation — country base + global regime + hyperinflation kick
            inf = inf_base + inflation_regime(year) + random.gauss(0, 0.6)
            inf = hyperinflation_kick(iso, year, inf)
            # Clip non-hyperinflation inflation to 0-15
            if iso not in ("VEN", "ARG", "TUR"):
                inf = max(-2.0, min(inf, 15.0))

            # Unemployment
            unemp = unemp_base + random.gauss(0, 0.4)
            if (year == 2009 and month >= 1) or (year == 2010 and month <= 6):
                unemp += 2.5  # GFC labour-market lag
            if year == 2020 and 4 <= month <= 12:
                unemp += 3.5  # COVID shock
            if year == 2021:
                unemp += 1.5
            unemp = max(2.0, min(unemp, 30.0))

            # 1% of country-months don't report unemployment
            unemp_value: float | None = unemp
            if random.random() < 0.01:
                unemp_value = None

            # Policy rate
            policy_baseline = 4.0 if advanced else 6.5
            if iso in ("CHE", "JPN"):
                policy_baseline = 0.5
            if iso == "TUR":
                policy_baseline = 12.0
            if iso == "ARG":
                policy_baseline = 30.0
            if iso == "VEN":
                policy_baseline = 25.0
            policy = policy_rate_regime(year, policy_baseline) + random.gauss(0, 0.15)
            policy = max(-0.75, policy)
            policy_value: float | None = policy
            # CHN policy_rate is NULL pre-2015 (managed-rate era — "data quality varies by source")
            if iso == "CHN" and year < 2015:
                policy_value = None

            # FX
            fx = fx_drift(year, iso, fx_base) * (1.0 + random.gauss(0, 0.005))

            # Current account
            ca_base = -1.5 if iso in ("USA", "GBR", "TUR", "BRA", "ZAF", "ARG") else 1.5
            if iso in ("DEU", "JPN", "CHN", "NOR", "CHE", "SAU", "NLD", "SGP", "ARE"):
                ca_base = 4.5
            ca = ca_base + random.gauss(0, 0.8)
            ca = max(-12.0, min(ca, 12.0))

            # Debt: baseline + crisis-driven jumps
            debt_pct = debt_pct + random.gauss(0, 0.3)
            if year == 2009:
                debt_pct += 1.5
            if year == 2020:
                debt_pct += 2.0
            debt_pct = max(15.0, min(debt_pct, 320.0))

            # Population — slow growth, advanced countries flatter
            pop_growth = 0.0008 if advanced else 0.0017
            pop = pop * (1.0 + pop_growth)

            row = {
                "country": iso,
                "country_name": name,
                "region": region,
                "month": f"{year:04d}-{month:02d}-01",
                "gdp_usd_bn": round(gdp, 2),
                "gdp_growth_yoy": round(gdp_growth_yoy, 3),
                "inflation_cpi_yoy": round(inf, 3),
                "unemployment_rate": "" if unemp_value is None else round(unemp_value, 2),
                "policy_rate": "" if policy_value is None else round(policy_value, 3),
                "fx_usd": round(fx, 4),
                "current_account_pct_gdp": round(ca, 2),
                "government_debt_pct_gdp": round(debt_pct, 2),
                "population_millions": round(pop, 3),
                "is_advanced_economy": "true" if advanced else "false",
            }
            rows.append(row)

    fieldnames = [
        "country",
        "country_name",
        "region",
        "month",
        "gdp_usd_bn",
        "gdp_growth_yoy",
        "inflation_cpi_yoy",
        "unemployment_rate",
        "policy_rate",
        "fx_usd",
        "current_account_pct_gdp",
        "government_debt_pct_gdp",
        "population_millions",
        "is_advanced_economy",
    ]

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    size_bytes = os.path.getsize(OUT_PATH)
    size_kb = size_bytes / 1024.0

    print(f"Wrote {OUT_PATH}")
    print(f"Rows:   {len(rows):,}")
    print(f"Size:   {size_bytes:,} bytes ({size_kb:,.1f} KB)")

    if not (600 * 1024 <= size_bytes <= 2_500 * 1024):
        raise SystemExit(
            f"File size {size_kb:.1f} KB outside target band 600-2500 KB; "
            f"adjust generator (rows or precision) and re-run."
        )
    print("Size within target band 600-2500 KB.")


if __name__ == "__main__":
    main()

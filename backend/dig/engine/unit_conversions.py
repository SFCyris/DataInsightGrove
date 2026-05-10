"""Unit registry for the `convert_units` step.

Each unit is stored as a linear conversion to a category-specific BASE unit:

    x_base = x_unit * factor + offset

For purely linear units (length, mass, volume, time, …) `offset` is 0 and
the formula simplifies. Temperature is the only category that uses a
non-zero offset (Celsius/Fahrenheit/Rankine all shift relative to Kelvin).

To convert from unit A to unit B in the same category, the step compiles
to a single SQL expression:

    ((x_a * factor_a + offset_a) - offset_b) / factor_b

The same formula compiles cleanly to a Polars expression and to a
generated Python script for `pnpm gen:python`.

OUT OF SCOPE intentionally:
  - Conversions that require external context (mol -> g needs molar
    mass, ppm -> mass needs density). Those are chemistry calculations,
    not unit conversions. A future `chemistry_calc` step would handle
    them with explicit context params.
  - Currency. Exchange rates change daily — that's a join against an
    external rates table, not a static conversion.
  - Compound units that aren't a single multiplicative factor (e.g.
    "convert km/h to mph" works because both decompose to length/time
    with the same time units cancelled, but "convert J/(kg·K) to
    BTU/(lb·°F)" is a multi-axis conversion better expressed as the
    product of length / mass / temperature conversions).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Unit:
    """One unit definition. `to_base(x) = x * factor + offset`."""
    id: str          # canonical identifier, used as enum value
    label: str       # human-facing display, e.g. "°C", "km/h"
    factor: float
    offset: float = 0.0


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    base_unit: str       # id of the base unit (factor=1, offset=0)
    description: str     # short tooltip for the category
    units: tuple[Unit, ...]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

# A thin helper for the linear-only categories that make up most of the
# registry. Only temperature uses non-zero offsets.
def _u(id: str, label: str, factor: float) -> Unit:
    return Unit(id=id, label=label, factor=factor, offset=0.0)


CATEGORIES: tuple[Category, ...] = (
    Category(
        id="temperature",
        label="Temperature",
        base_unit="kelvin",
        description="Convert between Celsius, Fahrenheit, Kelvin, and Rankine.",
        units=(
            Unit(id="kelvin",     label="K",   factor=1.0,    offset=0.0),
            Unit(id="celsius",    label="°C",  factor=1.0,    offset=273.15),
            # Fahrenheit to Kelvin: K = (F + 459.67) * 5/9 = F*5/9 + 459.67*5/9
            Unit(id="fahrenheit", label="°F",  factor=5.0/9,  offset=459.67 * 5.0/9),
            # Rankine to Kelvin: K = R * 5/9
            Unit(id="rankine",    label="°R",  factor=5.0/9,  offset=0.0),
        ),
    ),

    Category(
        id="length",
        label="Length",
        base_unit="meter",
        description="Distance and dimensional measurement.",
        units=(
            _u("meter",          "m",     1.0),
            _u("kilometer",      "km",    1_000.0),
            _u("centimeter",     "cm",    0.01),
            _u("millimeter",     "mm",    0.001),
            _u("micrometer",     "µm",    1e-6),
            _u("nanometer",      "nm",    1e-9),
            _u("inch",           "in",    0.0254),
            _u("foot",           "ft",    0.3048),
            _u("yard",           "yd",    0.9144),
            _u("mile",           "mi",    1609.344),
            _u("nautical_mile",  "nmi",   1852.0),
        ),
    ),

    Category(
        id="mass",
        label="Mass",
        base_unit="kilogram",
        description="Mass / weight in metric and imperial units.",
        units=(
            _u("kilogram",       "kg",     1.0),
            _u("gram",           "g",      0.001),
            _u("milligram",      "mg",     1e-6),
            _u("microgram",      "µg",     1e-9),
            _u("metric_ton",     "t",      1_000.0),
            _u("pound",          "lb",     0.45359237),
            _u("ounce",          "oz",     0.028349523125),
            _u("short_ton",      "ton(US)",  907.18474),
            _u("long_ton",       "ton(UK)",  1016.0469088),
            _u("stone",          "st",     6.35029318),
            _u("carat",          "ct",     0.0002),
        ),
    ),

    Category(
        id="volume",
        label="Volume",
        base_unit="liter",
        description="Volume / capacity (metric, US, and Imperial).",
        units=(
            _u("liter",            "L",       1.0),
            _u("milliliter",       "mL",      0.001),
            _u("cubic_meter",      "m³",      1000.0),
            _u("cubic_centimeter", "cm³",     0.001),
            _u("us_gallon",        "gal(US)", 3.785411784),
            _u("uk_gallon",        "gal(UK)", 4.54609),
            _u("us_quart",         "qt(US)",  0.946352946),
            _u("us_pint",          "pt(US)",  0.473176473),
            _u("us_fluid_ounce",   "fl oz(US)", 0.0295735295625),
            _u("uk_fluid_ounce",   "fl oz(UK)", 0.0284130625),
            _u("us_cup",           "cup(US)", 0.2365882365),
            _u("us_tablespoon",    "tbsp(US)", 0.01478676478125),
            _u("us_teaspoon",      "tsp(US)", 0.00492892159375),
        ),
    ),

    Category(
        id="time",
        label="Time",
        base_unit="second",
        description="Time durations.",
        units=(
            _u("second",      "s",  1.0),
            _u("nanosecond",  "ns", 1e-9),
            _u("microsecond", "µs", 1e-6),
            _u("millisecond", "ms", 1e-3),
            _u("minute",      "min", 60.0),
            _u("hour",        "hr",  3600.0),
            _u("day",         "day", 86400.0),
            _u("week",        "wk",  604800.0),
        ),
    ),

    Category(
        id="pressure",
        label="Pressure",
        base_unit="pascal",
        description="Pressure / stress (Pa, atmospheres, psi, mmHg, etc.).",
        units=(
            _u("pascal",     "Pa",   1.0),
            _u("kilopascal", "kPa",  1_000.0),
            _u("megapascal", "MPa",  1_000_000.0),
            _u("bar",        "bar",  100_000.0),
            _u("atmosphere", "atm",  101_325.0),
            _u("psi",        "psi",  6_894.757293168361),
            _u("torr",       "torr", 133.3223684211),
            _u("mmhg",       "mmHg", 133.3223684211),
            _u("inhg",       "inHg", 3_386.388157894735),
        ),
    ),

    Category(
        id="energy",
        label="Energy",
        base_unit="joule",
        description="Energy / heat / work.",
        units=(
            _u("joule",       "J",     1.0),
            _u("kilojoule",   "kJ",    1_000.0),
            _u("megajoule",   "MJ",    1_000_000.0),
            _u("calorie",     "cal",   4.184),
            _u("kilocalorie", "kcal",  4_184.0),
            _u("watt_hour",   "Wh",    3_600.0),
            _u("kilowatt_hour", "kWh", 3_600_000.0),
            _u("megawatt_hour", "MWh", 3_600_000_000.0),
            _u("btu",         "BTU",   1_055.05585262),
            _u("electronvolt", "eV",   1.602176634e-19),
        ),
    ),

    Category(
        id="power",
        label="Power",
        base_unit="watt",
        description="Power (rate of energy transfer).",
        units=(
            _u("watt",         "W",   1.0),
            _u("kilowatt",     "kW",  1_000.0),
            _u("megawatt",     "MW",  1_000_000.0),
            _u("horsepower_mech", "hp(mech)", 745.6998715822702),
            _u("horsepower_metric", "hp(metric)", 735.49875),
            _u("btu_per_hour", "BTU/hr", 0.29307107),
        ),
    ),

    Category(
        id="force",
        label="Force",
        base_unit="newton",
        description="Force.",
        units=(
            _u("newton",        "N",    1.0),
            _u("kilonewton",    "kN",   1_000.0),
            _u("pound_force",   "lbf",  4.4482216152605),
            _u("dyne",          "dyne", 1e-5),
            _u("kilogram_force", "kgf", 9.80665),
        ),
    ),

    Category(
        id="speed",
        label="Speed",
        base_unit="meter_per_second",
        description="Linear velocity.",
        units=(
            _u("meter_per_second", "m/s",  1.0),
            _u("kilometer_per_hour", "km/h", 1.0/3.6),
            _u("mile_per_hour",  "mph",  0.44704),
            _u("knot",           "knot", 0.514444444444),
            _u("foot_per_second", "ft/s", 0.3048),
        ),
    ),

    Category(
        id="angle",
        label="Angle",
        base_unit="radian",
        description="Plane angle.",
        units=(
            _u("radian",   "rad",  1.0),
            _u("degree",   "°",    0.017453292519943295),  # π / 180
            _u("gradian",  "grad", 0.015707963267948967),  # π / 200
            _u("arcminute", "'",   0.0002908882086657216),  # π / (180·60)
            _u("arcsecond", '"',   4.848136811095360e-06),  # π / (180·3600)
            _u("turn",     "tr",   6.283185307179586),     # 2π
        ),
    ),

    Category(
        id="frequency",
        label="Frequency",
        base_unit="hertz",
        description="Frequency / repetition rate.",
        units=(
            _u("hertz",      "Hz",   1.0),
            _u("kilohertz",  "kHz",  1_000.0),
            _u("megahertz",  "MHz",  1_000_000.0),
            _u("gigahertz",  "GHz",  1_000_000_000.0),
            _u("rpm",        "rpm",  1.0/60.0),
        ),
    ),

    Category(
        id="data_decimal",
        label="Data (decimal)",
        base_unit="byte",
        description="Data sizes using decimal (SI) prefixes — KB = 1000 B.",
        units=(
            _u("bit",      "bit",  0.125),
            _u("byte",     "B",    1.0),
            _u("kilobyte", "KB",   1_000.0),
            _u("megabyte", "MB",   1_000_000.0),
            _u("gigabyte", "GB",   1_000_000_000.0),
            _u("terabyte", "TB",   1_000_000_000_000.0),
            _u("petabyte", "PB",   1_000_000_000_000_000.0),
        ),
    ),

    Category(
        id="data_binary",
        label="Data (binary)",
        base_unit="byte_bin",
        description="Data sizes using binary (IEC) prefixes — KiB = 1024 B.",
        units=(
            _u("byte_bin",     "B",   1.0),
            _u("kibibyte",     "KiB", 1024.0),
            _u("mebibyte",     "MiB", 1024.0**2),
            _u("gibibyte",     "GiB", 1024.0**3),
            _u("tebibyte",     "TiB", 1024.0**4),
            _u("pebibyte",     "PiB", 1024.0**5),
        ),
    ),

    Category(
        id="substance",
        label="Substance (mol)",
        base_unit="mole",
        description="Amount of substance. Mol↔grams requires molar mass — out of scope.",
        units=(
            _u("mole",       "mol",  1.0),
            _u("millimole",  "mmol", 0.001),
            _u("micromole",  "µmol", 1e-6),
            _u("nanomole",   "nmol", 1e-9),
            _u("kilomole",   "kmol", 1_000.0),
        ),
    ),

    Category(
        id="molarity",
        label="Molarity",
        base_unit="molar",
        description="Concentration as moles per liter.",
        units=(
            _u("molar",       "M",   1.0),
            _u("millimolar",  "mM",  0.001),
            _u("micromolar",  "µM",  1e-6),
            _u("nanomolar",   "nM",  1e-9),
        ),
    ),
)


# Lookup index: unit_id -> (Category, Unit)
_INDEX: dict[str, tuple[Category, Unit]] = {
    u.id: (c, u) for c in CATEGORIES for u in c.units
}


def find_unit(unit_id: str) -> tuple[Category, Unit] | None:
    """Resolve a unit id to its (category, unit). Returns None on miss."""
    return _INDEX.get(unit_id)


def all_unit_ids() -> list[str]:
    """All unit ids across every category — flat list for the manifest enum."""
    return [u.id for c in CATEGORIES for u in c.units]


def category_for(unit_id: str) -> str | None:
    hit = find_unit(unit_id)
    return hit[0].id if hit else None


def conversion_factors(from_id: str, to_id: str) -> tuple[float, float, float, float]:
    """Return (factor_a, offset_a, factor_b, offset_b) for the formula:

        x_b = ((x_a * factor_a + offset_a) - offset_b) / factor_b

    Raises ValueError if the units are unknown or in different categories.
    """
    fa = find_unit(from_id)
    fb = find_unit(to_id)
    if fa is None:
        raise ValueError(f"convert_units: unknown from_unit {from_id!r}")
    if fb is None:
        raise ValueError(f"convert_units: unknown to_unit {to_id!r}")
    cat_a, ua = fa
    cat_b, ub = fb
    if cat_a.id != cat_b.id:
        raise ValueError(
            f"convert_units: {from_id!r} ({cat_a.id}) and {to_id!r} ({cat_b.id}) "
            "are in different categories — pick units from the same category."
        )
    return (ua.factor, ua.offset, ub.factor, ub.offset)


def convert_value(value: float, from_id: str, to_id: str) -> float:
    """Convert one numeric value. Used by tests + ad-hoc Python callers.

    The step itself doesn't go through this — it generates SQL / Polars
    expressions that run inside the engine. This is for unit testing the
    correctness of the registry without round-tripping through DuckDB.
    """
    fa, oa, fb, ob = conversion_factors(from_id, to_id)
    return ((value * fa + oa) - ob) / fb

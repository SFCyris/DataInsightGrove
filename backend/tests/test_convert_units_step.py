"""Tests for the convert_units step.

Three layers:
  1. Registry sanity — known-value spot checks for each category, including
     the cross-category rejection that catches user typos.
  2. Step output (Polars + SQL) — round-trips the same data through both
     engines and checks the outputs match within float precision.
  3. Schema + lineage — convert_units always produces a DOUBLE; lineage
     points back to the source column with a "converted from X to Y"
     transform label.
"""
from __future__ import annotations

import math

import duckdb
import polars as pl
import pytest

from dig.engine.registry import steps
from dig.engine.unit_conversions import (
    CATEGORIES,
    convert_value,
    conversion_factors,
    find_unit,
)


step = steps().get("convert_units")


# ---------- 1. Registry --------------------------------------------------


def test_registry_loads_all_units():
    """Every unit id is unique and resolvable, and every category's
    `base_unit` actually exists in its unit list."""
    seen = set()
    for cat in CATEGORIES:
        unit_ids = {u.id for u in cat.units}
        assert cat.base_unit in unit_ids, f"{cat.id} base_unit {cat.base_unit} not in units"
        for u in cat.units:
            assert u.id not in seen, f"duplicate unit id: {u.id}"
            seen.add(u.id)
            # Base unit must have factor=1 and offset=0.
            if u.id == cat.base_unit:
                assert u.factor == 1.0, f"{u.id} is base but factor != 1"
                assert u.offset == 0.0, f"{u.id} is base but offset != 0"


@pytest.mark.parametrize("value, fr, to, expected", [
    # Temperature — the only category with non-zero offsets.
    (0.0,    "celsius",     "fahrenheit", 32.0),
    (100.0,  "celsius",     "fahrenheit", 212.0),
    (-40.0,  "celsius",     "fahrenheit", -40.0),
    (273.15, "kelvin",      "celsius",    0.0),
    (0.0,    "celsius",     "kelvin",     273.15),
    (491.67, "rankine",     "fahrenheit", 32.0),
    # Pure-linear families.
    (1.0,    "kilometer",   "meter",      1_000.0),
    (1.0,    "mile",        "kilometer",  1.609344),
    (1.0,    "pound",       "gram",       453.59237),
    (1.0,    "us_gallon",   "liter",      3.785411784),
    (3600.0, "second",      "hour",       1.0),
    (1.0,    "atmosphere",  "pascal",     101_325.0),
    (1.0,    "kilowatt_hour", "megajoule", 3.6),
    (60.0,   "rpm",         "hertz",      1.0),
    (1.0,    "kibibyte",    "byte_bin",   1024.0),
    (180.0,  "degree",      "radian",     math.pi),
    # Chemistry.
    (1.0,    "mole",        "millimole",  1_000.0),
    (1.0,    "molar",       "millimolar", 1_000.0),
])
def test_known_conversions(value, fr, to, expected):
    got = convert_value(value, fr, to)
    assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-9), \
        f"{value} {fr} -> {to}: got {got}, expected {expected}"


def test_cross_category_conversion_rejected():
    with pytest.raises(ValueError, match="different categories"):
        conversion_factors("celsius", "kilometer")


def test_unknown_unit_rejected():
    with pytest.raises(ValueError, match="unknown"):
        conversion_factors("not_a_unit", "celsius")
    assert find_unit("does_not_exist") is None


# ---------- 2. Step output (Polars + SQL parity) -------------------------


def _values_close(a: list[float], b: list[float], tol: float = 1e-9) -> bool:
    return all(math.isclose(x, y, rel_tol=tol, abs_tol=tol) for x, y in zip(a, b))


@pytest.mark.parametrize("fr, to, vals", [
    ("celsius", "fahrenheit", [0.0, 100.0, -40.0, 25.5]),
    ("kilometer", "mile", [1.0, 0.0, 100.0, 1.609344]),
    ("us_gallon", "liter", [1.0, 5.0, 0.5]),
    ("kilowatt_hour", "joule", [1.0, 0.5, 10.0]),
    ("kibibyte", "byte_bin", [1.0, 1024.0]),
    ("mole", "millimole", [1.0, 0.001, 1_000.0]),
])
def test_step_polars_sql_parity(fr: str, to: str, vals: list[float]) -> None:
    """Polars and DuckDB SQL must produce the same output."""
    df = pl.DataFrame({"v": vals})
    params = {"column": "v", "from_unit": fr, "to_unit": to, "output_column": "out"}

    # Polars path
    pl_result = step.execute_polars({"in": df}, params).output
    pl_out = pl_result["out"].to_list()

    # SQL path
    con = duckdb.connect(":memory:")
    con.register("src", df)
    sql = step.to_sql(params, {"in": "src"})
    sql_out = con.execute(sql).pl()["out"].to_list()

    assert _values_close(pl_out, sql_out), f"polars {pl_out} != sql {sql_out}"


def test_step_in_place_overrides_source_column():
    """When output_column is empty, the source column is overwritten."""
    df = pl.DataFrame({"temp_c": [0.0, 100.0]})
    params = {"column": "temp_c", "from_unit": "celsius", "to_unit": "fahrenheit"}
    res = step.execute_polars({"in": df}, params).output
    assert res.columns == ["temp_c"]
    assert _values_close(res["temp_c"].to_list(), [32.0, 212.0])


def test_step_creates_new_column_when_output_set():
    df = pl.DataFrame({"temp_c": [0.0, 100.0]})
    params = {
        "column": "temp_c", "from_unit": "celsius", "to_unit": "fahrenheit",
        "output_column": "temp_f",
    }
    res = step.execute_polars({"in": df}, params).output
    assert res.columns == ["temp_c", "temp_f"]
    assert _values_close(res["temp_f"].to_list(), [32.0, 212.0])


# ---------- 3. Schema + lineage ------------------------------------------


def test_infer_schema_yields_double():
    """Conversion always produces a DOUBLE — even integer input goes
    through a multiplicative factor that almost always produces non-integer
    results."""
    schema = step.infer_schema(
        {"in": {"temp_c": "integer", "other": "string"}},
        {"column": "temp_c", "from_unit": "celsius", "to_unit": "fahrenheit"},
    )
    assert schema["temp_c"] == "double"


def test_column_dependencies_in_place():
    """In-place: source column lineage points back to itself with the
    'converted from X to Y' transform label. Other columns are passthrough."""
    deps = step.column_dependencies(
        {"column": "temp_c", "from_unit": "celsius", "to_unit": "fahrenheit"},
        {"in": {"temp_c": "integer", "label": "string"}},
    )
    assert "celsius to fahrenheit" in deps["temp_c"].transform
    assert deps["temp_c"].sources[0].column == "temp_c"
    assert deps["label"].transform == "passthrough"


def test_column_dependencies_new_column():
    """New column: original col is passthrough, new col is derived."""
    deps = step.column_dependencies(
        {
            "column": "temp_c", "from_unit": "celsius", "to_unit": "fahrenheit",
            "output_column": "temp_f",
        },
        {"in": {"temp_c": "integer", "label": "string"}},
    )
    assert deps["temp_c"].transform == "passthrough"
    assert "celsius to fahrenheit" in deps["temp_f"].transform
    assert deps["temp_f"].sources[0].column == "temp_c"

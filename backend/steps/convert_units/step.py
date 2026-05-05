"""convert_units step — convert a numeric column between units.

Compiles to a single SQL formula (DuckDB-compatible, browser-safe) and
to an equivalent Polars expression. The same unit registry powers both.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import (
    ColumnLineage,
    ColumnRef,
    PolarsContext,
    PolarsResult,
    Step,
    quote_ident,
)

from dig.engine.unit_conversions import conversion_factors, find_unit  # noqa: F401


def _resolve_output_name(params: dict[str, Any]) -> tuple[str, str, bool]:
    """Returns (source_col, output_col, in_place)."""
    src = params["column"]
    out = (params.get("output_column") or "").strip()
    if not out:
        return src, src, True
    return src, out, out == src


def _formula_sql(col: str, from_unit: str, to_unit: str) -> str:
    """Build the SQL expression that converts `col` from `from_unit` to
    `to_unit`. Single linear formula handles every category — temperature
    is the only one with non-zero offsets, but the form is the same."""
    fa, oa, fb, ob = conversion_factors(from_unit, to_unit)
    col_q = quote_ident(col)
    # Optimize the common pure-linear case: no offsets, no division.
    if oa == 0.0 and ob == 0.0:
        ratio = fa / fb
        if ratio == 1.0:
            # Same unit (or aliases like byte / byte_bin) — passthrough.
            return col_q
        return f"({col_q} * {ratio:.17g})"
    # General form: x_b = ((x_a * factor_a + offset_a) - offset_b) / factor_b
    return f"((({col_q} * {fa:.17g}) + {oa:.17g}) - {ob:.17g}) / {fb:.17g}"


def _formula_polars(col: str, from_unit: str, to_unit: str) -> pl.Expr:
    """Polars equivalent of `_formula_sql`. Used by execute_polars."""
    fa, oa, fb, ob = conversion_factors(from_unit, to_unit)
    expr = pl.col(col)
    if oa == 0.0 and ob == 0.0:
        ratio = fa / fb
        if ratio == 1.0:
            return expr
        return expr * ratio
    return ((expr * fa + oa) - ob) / fb


class ConvertUnitsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        from_u = params["from_unit"]
        to_u = params["to_unit"]
        col, out, in_place = _resolve_output_name(params)
        formula = _formula_sql(col, from_u, to_u)
        if in_place:
            return f"SELECT * REPLACE ({formula} AS {quote_ident(col)}) FROM {src}"
        return f"SELECT *, {formula} AS {quote_ident(out)} FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        col, out, _ = _resolve_output_name(params)
        # Result is always DOUBLE (the formula divides). Even integer-typed
        # input becomes a real number after the conversion factor.
        if col in s:
            s[out] = "double"
        return s

    def column_dependencies(
        self,
        params: dict[str, Any],
        input_schemas: dict[str, dict[str, str]],
    ) -> dict[str, ColumnLineage]:
        col, out, in_place = _resolve_output_name(params)
        from_u = params.get("from_unit", "?")
        to_u = params.get("to_unit", "?")
        in_cols = input_schemas.get("in") or {}

        deps: dict[str, ColumnLineage] = {}

        # Carry every other column through unchanged (per the SELECT * shape).
        for c in in_cols:
            if in_place and c == col:
                # In-place: source column becomes the converted output.
                deps[c] = ColumnLineage(
                    sources=[ColumnRef(port="in", column=col)],
                    transform=f"converted from {from_u} to {to_u}",
                )
            elif (not in_place) and c == out:
                # Edge case: user named the new column the same as another
                # existing column — SQL `SELECT *, x AS y` would collide.
                # Surface lineage as if it overwrote.
                deps[c] = ColumnLineage(
                    sources=[ColumnRef(port="in", column=col)],
                    transform=f"converted from {from_u} to {to_u}",
                )
            else:
                deps[c] = ColumnLineage(
                    sources=[ColumnRef(port="in", column=c)],
                    transform="passthrough",
                )

        # New output column (when not in-place).
        if not in_place and out not in deps:
            deps[out] = ColumnLineage(
                sources=[ColumnRef(port="in", column=col)],
                transform=f"converted from {from_u} to {to_u}",
            )
        return deps

    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        from_u = params["from_unit"]
        to_u = params["to_unit"]
        col, out, _ = _resolve_output_name(params)
        if col not in df.columns:
            raise ValueError(f"convert_units: column {col!r} not in input")
        # Validate the unit pair early so we get a clear error rather than
        # the LazyFrame raising on collect.
        conversion_factors(from_u, to_u)
        new_df = df.with_columns(_formula_polars(col, from_u, to_u).alias(out))
        return PolarsResult(output=new_df)


step = ConvertUnitsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""Resample step — bucket time-series rows into fixed intervals and aggregate.

Polars's `group_by_dynamic` does the heavy lifting. We add gap-filling so the
output has a row for every bucket — important for plotting + downstream
rolling-window steps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step

_AGG_FUNCS = {
    "sum":    lambda col: pl.col(col).sum(),
    "mean":   lambda col: pl.col(col).mean(),
    "median": lambda col: pl.col(col).median(),
    "min":    lambda col: pl.col(col).min(),
    "max":    lambda col: pl.col(col).max(),
    "count":  lambda col: pl.col(col).count(),
    "std":    lambda col: pl.col(col).std(),
    "first":  lambda col: pl.col(col).first(),
    "last":   lambda col: pl.col(col).last(),
}


class ResampleStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        tcol = (params.get("time_column") or "").strip()
        interval = (params.get("interval") or "1d").strip()
        aggs = params.get("aggregations") or []

        if not tcol or tcol not in df.columns:
            raise ValueError("resample: 'time_column' is required and must exist")
        if not aggs:
            raise ValueError("resample: 'aggregations' must not be empty")

        # Coerce time column to datetime if it's a string.
        if df.schema[tcol] == pl.Utf8:
            df = df.with_columns(pl.col(tcol).str.to_datetime(strict=False))

        df = df.sort(tcol)

        agg_exprs: list[pl.Expr] = []
        for a in aggs:
            col = (a.get("column") or "").strip()
            fn = (a.get("fn") or "").lower()
            alias = (a.get("as") or f"{col}_{fn}").strip()
            if fn not in _AGG_FUNCS:
                raise ValueError(f"resample: unsupported aggregation fn '{fn}'")
            if col not in df.columns:
                raise ValueError(f"resample: aggregation column '{col}' missing")
            agg_exprs.append(_AGG_FUNCS[fn](col).alias(alias))

        bucketed = df.group_by_dynamic(
            tcol, every=interval, period=interval, label="left",
        ).agg(agg_exprs).sort(tcol)

        # Optional gap-fill — produce a row for every bucket between the data
        # min and max, even if no rows fell in it.
        if bool(params.get("fill_gaps", True)) and bucketed.height >= 1:
            t_min = bucketed.get_column(tcol).min()
            t_max = bucketed.get_column(tcol).max()
            # `pl.datetime_range` returns a default-precision datetime; the
            # source column may be a different precision (μs vs ns) depending
            # on whether it came from DuckDB-cached Parquet, raw CSV, or a
            # Python list. Cast to the bucketed dtype before the join.
            full_range = pl.datetime_range(t_min, t_max, interval=interval, eager=True)
            full = pl.DataFrame({tcol: full_range}).with_columns(
                pl.col(tcol).cast(bucketed.schema[tcol])
            )
            bucketed = full.join(bucketed, on=tcol, how="left").sort(tcol)

            fill_value = (params.get("fill_value") or "null").lower()
            if fill_value == "0":
                # Fill numeric columns with 0; leave others null.
                for c in bucketed.columns:
                    if c == tcol:
                        continue
                    dt = str(bucketed.schema[c]).lower()
                    if any(t in dt for t in ("int", "float", "double", "decimal")):
                        bucketed = bucketed.with_columns(pl.col(c).fill_null(0))

        return PolarsResult(output=bucketed)


step = ResampleStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

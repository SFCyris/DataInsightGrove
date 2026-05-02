"""Column profiling — runs in a single Polars pass per column class.

Returns a JSON-serializable dict consumed by the frontend's profile cards.
Designed to be cheap on multi-GB files: most stats use Polars expressions on
LazyFrame; expensive ops (value_counts) are bounded by top_k.

Includes a meta-type post-pass that promotes columns to 'index' (all-unique
integers) or 'timezone' (mostly IANA-valid strings) so the grid can flag
duplicates / invalid zones in red.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl

from dig.engine.meta_types import detect_index, detect_timezone_from_top

NUMERIC_DTYPES = (
    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
    pl.Float32, pl.Float64,
)
TEMPORAL_DTYPES = (pl.Date, pl.Datetime, pl.Time, pl.Duration)
STRING_DTYPES = (pl.Utf8, pl.String)
BOOL_DTYPES = (pl.Boolean,)
NESTED_DTYPES = (pl.List, pl.Struct)


def _logical_type(dtype: pl.DataType) -> str:
    if dtype in BOOL_DTYPES:
        return "boolean"
    if any(dtype == d or isinstance(dtype, d) for d in NUMERIC_DTYPES):
        return "integer" if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                      pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64) else "double"
    if any(isinstance(dtype, d) for d in TEMPORAL_DTYPES):
        return "datetime" if isinstance(dtype, (pl.Datetime, pl.Time)) else "date"
    if dtype in STRING_DTYPES:
        return "string"
    if any(isinstance(dtype, d) for d in NESTED_DTYPES):
        return "nested"
    return "string"


def _safe_num(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def profile_dataframe(
    lf: pl.LazyFrame,
    *,
    top_k: int = 10,
    sample_rows: int | None = 200_000,
) -> dict[str, Any]:
    """Compute schema + per-column statistics for a LazyFrame.

    sample_rows=None disables sampling for value_counts (heavier but exact).
    """
    schema = lf.collect_schema()
    columns = list(schema.keys())

    head_lf = lf if sample_rows is None else lf.head(sample_rows)

    # Single pass for cheap aggregates.
    aggs: list[pl.Expr] = [pl.len().alias("__row_count__")]
    for col in columns:
        aggs.extend([
            pl.col(col).null_count().alias(f"_null:{col}"),
            pl.col(col).n_unique().alias(f"_distinct:{col}"),
        ])
        dtype = schema[col]
        if any(dtype == d or isinstance(dtype, d) for d in NUMERIC_DTYPES):
            aggs.extend([
                pl.col(col).min().alias(f"_min:{col}"),
                pl.col(col).max().alias(f"_max:{col}"),
                pl.col(col).mean().alias(f"_mean:{col}"),
                pl.col(col).std().alias(f"_std:{col}"),
            ])
        elif dtype in STRING_DTYPES:
            aggs.extend([
                pl.col(col).str.len_chars().min().alias(f"_min:{col}"),
                pl.col(col).str.len_chars().max().alias(f"_max:{col}"),
                pl.col(col).str.len_chars().mean().alias(f"_mean:{col}"),
            ])
        elif any(isinstance(dtype, d) for d in TEMPORAL_DTYPES):
            aggs.extend([
                pl.col(col).min().cast(pl.Utf8).alias(f"_min:{col}"),
                pl.col(col).max().cast(pl.Utf8).alias(f"_max:{col}"),
            ])

    stats_row = head_lf.select(aggs).collect().to_dicts()[0]
    sampled_rows = stats_row["__row_count__"]

    columns_out: list[dict[str, Any]] = []
    for col in columns:
        dtype = schema[col]
        nulls = stats_row.get(f"_null:{col}")
        col_info: dict[str, Any] = {
            "name": col,
            "type": _logical_type(dtype),
            "polarsType": str(dtype),
            "nullCount": nulls,
            "nullFraction": (nulls / sampled_rows) if sampled_rows else None,
            "distinctCount": stats_row.get(f"_distinct:{col}"),
            "min": _safe_num(stats_row.get(f"_min:{col}")),
            "max": _safe_num(stats_row.get(f"_max:{col}")),
            "mean": _safe_num(stats_row.get(f"_mean:{col}")),
            "std": _safe_num(stats_row.get(f"_std:{col}")),
            "sampledRows": sampled_rows,
        }

        # Top-K value counts (categorical preview). Bounded by sample.
        try:
            vc = (
                head_lf.select(pl.col(col))
                .filter(pl.col(col).is_not_null())
                .collect()
                .to_series()
                .value_counts(sort=True)
                .head(top_k)
            )
            top: list[dict[str, Any]] = []
            value_col, count_col = vc.columns[0], vc.columns[1]
            for row in vc.iter_rows(named=True):
                v = row[value_col]
                if hasattr(v, "isoformat"):
                    v = v.isoformat()
                top.append({"value": v, "count": row[count_col]})
            col_info["topValues"] = top
        except Exception:
            col_info["topValues"] = []

        # Numeric histogram bins (for the profile sparkline).
        if col_info["type"] in ("integer", "double") and col_info["min"] is not None:
            try:
                bin_count = 20
                series = (
                    head_lf.select(pl.col(col))
                    .filter(pl.col(col).is_not_null())
                    .collect()
                    .to_series()
                )
                if len(series) and col_info["max"] != col_info["min"]:
                    hist = series.hist(bin_count=bin_count)
                    bins = []
                    for row in hist.iter_rows(named=True):
                        # column names vary across polars versions; pick numeric + count
                        keys = list(row.keys())
                        # heuristic: last column is count
                        bins.append({
                            "bin": row[keys[0]] if not isinstance(row[keys[0]], (int, float)) else row[keys[0]],
                            "count": row[keys[-1]],
                        })
                    col_info["histogram"] = bins
            except Exception:
                pass

        columns_out.append(col_info)

    # Meta-type post-pass — promote integer columns with all-unique values
    # to 'index' and string columns whose top values are valid IANA zones to
    # 'timezone'. Done after the main loop so the detection has full
    # access to nullCount/distinctCount/topValues. Cheap (O(columns))
    # because the underlying stats are already computed.
    for ci in columns_out:
        base = ci["type"]
        nulls = ci.get("nullCount") or 0
        non_null = (sampled_rows or 0) - nulls
        if base == "integer" and detect_index(
            distinct=ci.get("distinctCount"),
            non_null=non_null,
            sampled=sampled_rows,
        ):
            ci["type"] = "index"
        elif base == "string" and detect_timezone_from_top(ci.get("topValues") or []):
            ci["type"] = "timezone"

    return {
        "rowCountSampled": sampled_rows,
        "columns": columns_out,
    }

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

from dig.engine.meta_types import ALTERNATE_MIN_SCORE, detect_candidates, descriptor

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

    # Meta-type post-pass — every detector in the type registry runs
    # against every column's profile and returns a TypeCandidate or None.
    # The highest-scoring candidate becomes the column's primary `type`;
    # remaining candidates with score ≥ ALTERNATE_MIN_SCORE are attached
    # as `candidates` so the UI can show "DIG picked X but it could also
    # be Y or Z" with a smart-picks-first cast dropdown.
    #
    # The base physical type (string/integer/double/…) is always part of
    # the candidate list as a fallback so the user can explicitly cast
    # back. It's added with score=1.0 only when no detector wins, otherwise
    # with a low score so it ranks below detected meta-types.
    for ci in columns_out:
        base = ci["type"]
        candidates = detect_candidates(ci)
        # Primary = top scorer (if any) or fall back to the base physical type.
        if candidates:
            ci["type"] = candidates[0].type_id
            # Storage choice: detector override wins, otherwise descriptor
            # default. Phase 1.4 surfaces this in the UI; Phase 1.3 uses it
            # to drive cast SQL.
            top = candidates[0]
            top_descriptor = descriptor(top.type_id)
            ci["storage"] = top.storage or (top_descriptor.sql_type if top_descriptor else None)
        else:
            # No detector won — storage is just the base physical type's
            # natural SQL form. base is already the logical name (string,
            # integer, double, …); the cast SQL map handles the mapping.
            ci["storage"] = None  # populated by /datasets serializer if needed
        # Build a UI-facing list: detected candidates above ALTERNATE_MIN_SCORE,
        # plus the base type as the universal fallback at the bottom. Carry
        # the storage hint per-candidate so the Cast UI can show "currency
        # → DECIMAL(18,4)" / "scientific → VARCHAR" tooltips.
        ui_candidates = [
            {
                "type": c.type_id,
                "score": round(c.score, 3),
                "reason": c.reason,
                "storage": c.storage or (descriptor(c.type_id).sql_type if descriptor(c.type_id) else None),
            }
            for c in candidates if c.score >= ALTERNATE_MIN_SCORE
        ]
        # Always include the base physical type — it's the "give me back the
        # raw, unconstrained representation" option in the cast dropdown.
        if not any(c["type"] == base for c in ui_candidates):
            ui_candidates.append({
                "type": base,
                "score": 0.50 if candidates else 1.0,
                "reason": "base physical type",
                "storage": None,
            })
        ci["candidates"] = ui_candidates

    return {
        "rowCountSampled": sampled_rows,
        "columns": columns_out,
    }

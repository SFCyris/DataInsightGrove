"""impute_mean_median_mode — fill nulls with column statistics."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


def _is_numeric(dtype: pl.DataType) -> bool:
    return dtype.is_numeric()


class ImputeMeanMedianModeStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        strategy = (params.get("strategy") or "auto").lower()
        if not cols:
            raise ValueError("impute_mean_median_mode: at least one column required")
        out = df
        per_col_strategy: dict[str, str] = {}
        per_col_value: dict[str, object] = {}
        for c in cols:
            if c not in out.columns: continue
            dtype = out.schema[c]
            chosen = strategy
            if chosen == "auto":
                chosen = "median" if _is_numeric(dtype) else "mode"
            try:
                if chosen == "mean":
                    val = out[c].drop_nulls().mean()
                elif chosen == "median":
                    val = out[c].drop_nulls().median()
                else:  # mode
                    non_null = out[c].drop_nulls()
                    val = non_null.mode()[0] if non_null.len() > 0 else None
            except Exception:
                val = None
            if val is not None:
                out = out.with_columns(pl.col(c).fill_null(val))
            per_col_strategy[c] = chosen
            per_col_value[c] = val
        return PolarsResult(output=out, artifacts=[{
            "kind": "metrics", "label": "Imputation summary",
            "data": {"strategy_per_column": per_col_strategy,
                     "value_used_per_column": {k: str(v) for k, v in per_col_value.items()}},
        }])


step = ImputeMeanMedianModeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

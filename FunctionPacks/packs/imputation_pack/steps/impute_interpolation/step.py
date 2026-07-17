"""impute_interpolation — fill numeric nulls via linear / nearest."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ImputeInterpolationStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        method = (params.get("method") or "linear").lower()
        sort_col = params.get("sortColumn")
        if sort_col and sort_col in df.columns:
            df = df.sort(sort_col)
        out = df
        for c in cols:
            if c not in out.columns: continue
            if method == "linear":
                out = out.with_columns(pl.col(c).interpolate())
            else:  # nearest = forward then backward fill
                out = out.with_columns(pl.col(c).forward_fill().backward_fill())
        return PolarsResult(output=out)


step = ImputeInterpolationStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

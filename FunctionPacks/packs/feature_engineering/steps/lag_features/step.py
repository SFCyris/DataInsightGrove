"""lag_features — add shifted-by-N versions of columns."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class LagFeaturesStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        lags = [int(x.strip()) for x in (params.get("lags") or "1").split(",") if x.strip()]
        sort_col = params.get("sortColumn")
        group_col = params.get("groupColumn")
        if sort_col and sort_col in df.columns:
            df = df.sort(sort_col)
        new_cols = []
        for c in cols:
            if c not in df.columns: continue
            for n in lags:
                if group_col and group_col in df.columns:
                    new_cols.append(pl.col(c).shift(n).over(group_col).alias(f"{c}_lag{n}"))
                else:
                    new_cols.append(pl.col(c).shift(n).alias(f"{c}_lag{n}"))
        out = df.with_columns(new_cols) if new_cols else df
        return PolarsResult(output=out)


step = LagFeaturesStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

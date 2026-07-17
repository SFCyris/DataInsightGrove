"""scale_robust — (x - median) / IQR per column."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ScaleRobustStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        suffix = params.get("suffix") or "_robust"
        new = []
        for c in cols:
            if c not in df.columns: continue
            med = df[c].median()
            q1 = df[c].quantile(0.25); q3 = df[c].quantile(0.75)
            iqr = (q3 or 0) - (q1 or 0) or 1.0
            new.append(((pl.col(c) - med) / iqr).alias(f"{c}{suffix}"))
        return PolarsResult(output=df.with_columns(new) if new else df)


step = ScaleRobustStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

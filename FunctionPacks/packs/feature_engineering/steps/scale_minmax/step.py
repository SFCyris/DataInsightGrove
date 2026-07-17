"""scale_minmax — rescale each column to [a, b]."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ScaleMinmaxStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        rmin = float(params.get("rangeMin", 0.0)); rmax = float(params.get("rangeMax", 1.0))
        suffix = params.get("suffix") or "_minmax"
        new = []
        for c in cols:
            if c not in df.columns: continue
            mn = df[c].min(); mx = df[c].max()
            span = (mx or 0) - (mn or 0) or 1.0
            new.append(
                (((pl.col(c) - mn) / span) * (rmax - rmin) + rmin).alias(f"{c}{suffix}")
            )
        return PolarsResult(output=df.with_columns(new) if new else df)


step = ScaleMinmaxStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

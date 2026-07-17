"""scale_standard — z-score per column."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ScaleStandardStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        suffix = params.get("suffix") or "_scaled"
        new = []
        for c in cols:
            if c not in df.columns: continue
            mu = df[c].mean(); sd = df[c].std()
            if sd is None or sd == 0:
                new.append(pl.lit(0.0).alias(f"{c}{suffix}"))
            else:
                new.append(((pl.col(c) - mu) / sd).alias(f"{c}{suffix}"))
        return PolarsResult(output=df.with_columns(new) if new else df)


step = ScaleStandardStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

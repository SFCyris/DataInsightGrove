"""target_encoding — replace category with smoothed mean of target."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class TargetEncodingStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cat = params["categoryColumn"]; target = params["targetColumn"]
        m = float(params.get("smoothing", 10.0))
        out_col = params.get("outputColumn") or "target_encoded"
        global_mean = float(df[target].drop_nulls().mean() or 0)
        agg = df.group_by(cat).agg([
            pl.col(target).mean().alias("__mean"),
            pl.len().alias("__n"),
        ]).with_columns(
            ((pl.col("__mean") * pl.col("__n") + global_mean * m) /
             (pl.col("__n") + m)).alias(out_col)
        ).select([cat, out_col])
        out = df.join(agg, on=cat, how="left")
        return PolarsResult(output=out)


step = TargetEncodingStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

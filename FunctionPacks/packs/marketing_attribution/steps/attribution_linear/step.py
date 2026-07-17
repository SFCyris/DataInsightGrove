"""attribution_linear — 1/N credit per touch in each journey."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class AttributionLinearStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; c = params["channelColumn"]; conv = params["convertedColumn"]
        converters = df.filter(pl.col(conv).cast(pl.Boolean))[u].unique().to_list()
        sub = df.filter(pl.col(u).is_in(converters))
        # Per user, count touches; credit per row = 1/count.
        sub = sub.with_columns(pl.len().over(u).alias("__touches"))
        sub = sub.with_columns((1.0 / pl.col("__touches")).alias("__credit"))
        out = sub.group_by(c).agg(pl.col("__credit").sum().alias("credited_conversions")).sort(
            "credited_conversions", descending=True
        ).rename({c: "channel"})
        return PolarsResult(output=out)


step = AttributionLinearStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""attribution_last_touch — 100% credit to chronologically last touch."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class AttributionLastTouchStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; c = params["channelColumn"]
        t = params["timestampColumn"]; conv = params["convertedColumn"]
        converters = df.filter(pl.col(conv).cast(pl.Boolean))[u].unique().to_list()
        sub = df.filter(pl.col(u).is_in(converters)).sort([u, t])
        last_touches = sub.group_by(u).agg(pl.col(c).last().alias("last_channel"))
        out = last_touches.group_by("last_channel").len().rename(
            {"len": "credited_conversions", "last_channel": "channel"}
        ).sort("credited_conversions", descending=True)
        return PolarsResult(output=out)


step = AttributionLastTouchStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

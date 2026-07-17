"""attribution_first_touch — 100% credit to chronologically first touch."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class AttributionFirstTouchStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; c = params["channelColumn"]
        t = params["timestampColumn"]; conv = params["convertedColumn"]
        # Filter to converters, then take their first touch.
        converters = df.filter(pl.col(conv).cast(pl.Boolean))[u].unique().to_list()
        sub = df.filter(pl.col(u).is_in(converters)).sort([u, t])
        first_touches = sub.group_by(u).agg(pl.col(c).first().alias("first_channel"))
        out = first_touches.group_by("first_channel").len().rename(
            {"len": "credited_conversions", "first_channel": "channel"}
        ).sort("credited_conversions", descending=True)
        return PolarsResult(output=out)


step = AttributionFirstTouchStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

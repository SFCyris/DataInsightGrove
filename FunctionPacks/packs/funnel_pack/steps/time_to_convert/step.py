"""time_to_convert — per-user time between first and last funnel event."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class TimeToConvertStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; t = params["timestampColumn"]; e = params["eventColumn"]
        first = params["firstEvent"]; last = params["lastEvent"]
        firsts = (df.filter(pl.col(e) == first)
                    .group_by(u).agg(pl.col(t).min().alias("__first_at")))
        lasts = (df.filter(pl.col(e) == last)
                   .group_by(u).agg(pl.col(t).min().alias("__last_at")))
        joined = firsts.join(lasts, on=u, how="inner")
        joined = joined.with_columns(
            (pl.col("__last_at") - pl.col("__first_at")).dt.total_seconds().alias("seconds_to_convert")
        ).with_columns(
            (pl.col("seconds_to_convert") / 3600).alias("hours_to_convert")
        )
        return PolarsResult(output=joined.sort("hours_to_convert"))


step = TimeToConvertStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

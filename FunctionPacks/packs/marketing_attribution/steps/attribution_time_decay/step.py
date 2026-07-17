"""attribution_time_decay — exponential decay credit by recency."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class AttributionTimeDecayStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; c = params["channelColumn"]
        t = params["timestampColumn"]; conv = params["convertedColumn"]
        half_life = float(params.get("halfLifeDays", 7.0))
        lam = math.log(2) / half_life

        converters = df.filter(pl.col(conv).cast(pl.Boolean))[u].unique().to_list()
        sub = df.filter(pl.col(u).is_in(converters))
        # For each user, conversion-time = max touch timestamp.
        sub = sub.with_columns(pl.col(t).max().over(u).alias("__conv_at"))
        sub = sub.with_columns(
            (pl.col("__conv_at") - pl.col(t)).dt.total_days().alias("__days_before")
        )
        sub = sub.with_columns(
            (pl.col("__days_before").cast(pl.Float64).map_elements(lambda d: math.exp(-lam * d), return_dtype=pl.Float64)).alias("__weight")
        )
        # Normalise per user so each journey contributes 1.
        sub = sub.with_columns((pl.col("__weight") / pl.col("__weight").sum().over(u)).alias("__credit"))
        out = sub.group_by(c).agg(pl.col("__credit").sum().alias("credited_conversions")).sort(
            "credited_conversions", descending=True
        ).rename({c: "channel"})
        return PolarsResult(output=out)


step = AttributionTimeDecayStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

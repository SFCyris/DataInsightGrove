"""retention_curve — average retention per period offset."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class RetentionCurveStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; s = params["signupDateColumn"]; a = params["activityDateColumn"]
        period = (params.get("period") or "month").lower()
        max_periods = int(params.get("maxPeriods", 12))

        days_per_period = {"week": 7, "month": 30, "quarter": 90}.get(period, 30)
        clean = df.drop_nulls(subset=[u, s, a]).with_columns([
            ((pl.col(a).cast(pl.Date) - pl.col(s).cast(pl.Date)).dt.total_days() //
             days_per_period).alias("__offset"),
            pl.col(s).cast(pl.Date).dt.truncate(f"{days_per_period}d").alias("__cohort"),
        ]).filter((pl.col("__offset") >= 0) & (pl.col("__offset") < max_periods))

        # Per-cohort users active in each offset.
        active = (clean.group_by(["__cohort", "__offset"])
                       .agg(pl.col(u).n_unique().alias("__active")))
        sizes = (clean.filter(pl.col("__offset") == 0)
                       .group_by("__cohort")
                       .agg(pl.col(u).n_unique().alias("__size")))
        joined = active.join(sizes, on="__cohort", how="left")
        joined = joined.with_columns(
            (pl.col("__active") / pl.col("__size")).alias("__rate")
        )
        # Average rate per offset.
        out = (joined.group_by("__offset")
                      .agg([
                          pl.col("__rate").mean().alias("retention_rate"),
                          pl.col("__cohort").n_unique().alias("n_cohorts"),
                      ])
                      .sort("__offset")
                      .rename({"__offset": "period_offset"}))
        return PolarsResult(output=out)


step = RetentionCurveStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

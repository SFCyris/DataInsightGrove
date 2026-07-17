"""multi_path_funnel — count users who completed N of M unordered steps."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class MultiPathFunnelStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; e = params["eventColumn"]
        targets = [s.strip() for s in params["targetSteps"].split(",") if s.strip()]
        target_set = set(targets)
        # Per user, the set of target steps they completed.
        per_user = (df.filter(pl.col(e).is_in(targets))
                       .group_by(u)
                       .agg(pl.col(e).unique().alias("__steps")))
        per_user = per_user.with_columns(
            pl.col("__steps").list.len().alias("steps_completed")
        )
        # Distribution.
        dist = per_user.group_by("steps_completed").len().sort("steps_completed").rename({"len": "users"})
        dist = dist.with_columns(
            (pl.col("users") / dist["users"].sum()).alias("share")
        )
        return PolarsResult(output=dist)


step = MultiPathFunnelStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""cohort_table — classic retention cohort matrix."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


_PERIOD_TO_DATE_FN = {"week": "1w", "month": "1mo", "quarter": "1q"}


class CohortTableStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; s = params["signupDateColumn"]; a = params["activityDateColumn"]
        period = (params.get("period") or "month").lower()
        output = (params.get("output") or "rate").lower()
        truncate = _PERIOD_TO_DATE_FN.get(period, "1mo")

        clean = df.drop_nulls(subset=[u, s, a]).with_columns([
            pl.col(s).cast(pl.Date).dt.truncate(truncate).alias("__cohort"),
            pl.col(a).cast(pl.Date).dt.truncate(truncate).alias("__activity"),
        ])
        # Compute period offset in months/weeks.
        if period == "week":
            clean = clean.with_columns(
                ((pl.col("__activity") - pl.col("__cohort")).dt.total_days() // 7).alias("__offset")
            )
        elif period == "quarter":
            clean = clean.with_columns(
                ((pl.col("__activity") - pl.col("__cohort")).dt.total_days() // 90).alias("__offset")
            )
        else:  # month
            clean = clean.with_columns(
                ((pl.col("__activity") - pl.col("__cohort")).dt.total_days() // 30).alias("__offset")
            )
        # Per cohort, count distinct users active in each period offset.
        agg = (clean.group_by(["__cohort", "__offset"])
                     .agg(pl.col(u).n_unique().alias("active_users")))
        # Cohort sizes (period 0).
        sizes = (clean.filter(pl.col("__offset") == 0)
                       .group_by("__cohort")
                       .agg(pl.col(u).n_unique().alias("cohort_size")))
        agg = agg.join(sizes, on="__cohort", how="left")
        if output == "rate":
            agg = agg.with_columns(
                (pl.col("active_users") / pl.col("cohort_size")).alias("retention_rate")
            )
        # Pivot to wide cohort table.
        value_col = "retention_rate" if output == "rate" else "active_users"
        wide = (agg.pivot(values=value_col, index="__cohort", on="__offset",
                           aggregate_function="first")
                    .sort("__cohort")
                    .rename({"__cohort": "cohort"}))
        return PolarsResult(output=wide)


step = CohortTableStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

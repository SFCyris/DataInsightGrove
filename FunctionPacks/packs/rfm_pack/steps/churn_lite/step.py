"""churn_lite — flag customers whose last activity is older than a window."""
from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ChurnLiteStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        c = params["customerColumn"]; d = params["dateColumn"]
        window_days = int(params.get("windowDays", 90))
        as_of_raw = (params.get("asOfDate") or "").strip()
        as_of = datetime.fromisoformat(as_of_raw).date() if as_of_raw else date.today()

        clean = df.drop_nulls(subset=[c, d])
        agg = (clean.group_by(c).agg([
            pl.col(d).max().alias("last_activity"),
            pl.col(d).count().alias("activity_count"),
        ]).with_columns([
            (pl.lit(as_of).cast(pl.Date) - pl.col("last_activity").cast(pl.Date))
                .dt.total_days().alias("days_since_last"),
        ]))
        out = agg.with_columns(
            (pl.col("days_since_last") > window_days).alias("is_churned"),
        )
        return PolarsResult(output=out)


step = ChurnLiteStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

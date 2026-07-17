"""ltv_with_discount — discounted lifetime value per customer."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class LtvWithDiscountStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        c = params["customerColumn"]; p = params["periodColumn"]; r = params["revenueColumn"]
        rate = float(params.get("discountRate", 0.05))
        clean = df.drop_nulls(subset=[c, p, r]).with_columns(
            (pl.col(r) / ((1 + rate) ** pl.col(p))).alias("__discounted")
        )
        out = clean.group_by(c).agg([
            pl.col("__discounted").sum().alias("ltv"),
            pl.col(r).sum().alias("undiscounted_total"),
            pl.col(p).max().alias("periods_observed"),
        ]).sort("ltv", descending=True)
        return PolarsResult(output=out)


step = LtvWithDiscountStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

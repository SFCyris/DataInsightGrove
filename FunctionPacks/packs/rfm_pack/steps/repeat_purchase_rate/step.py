"""repeat_purchase_rate — share of customers with N+ purchases."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class RepeatPurchaseRateStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        c = params["customerColumn"]
        d = params["dateColumn"]
        min_purchases = int(params.get("minPurchases", 2))
        group_col = params.get("groupColumn")

        clean = df.drop_nulls(subset=[c, d])
        if group_col and group_col in df.columns:
            # Per-group: customer counts per group, then fraction with >= min.
            customer_counts = clean.group_by([group_col, c]).len().rename({"len": "n_purchases"})
            agg = customer_counts.group_by(group_col).agg([
                pl.len().alias("n_customers"),
                (pl.col("n_purchases") >= min_purchases).sum().alias("n_repeat"),
            ]).with_columns(
                (pl.col("n_repeat") / pl.col("n_customers")).alias("repeat_rate")
            )
            return PolarsResult(output=agg.sort(group_col))
        # Global: single-row result.
        cust = clean.group_by(c).len().rename({"len": "n_purchases"})
        n_total = cust.height
        n_rep = cust.filter(pl.col("n_purchases") >= min_purchases).height
        out = pl.DataFrame({
            "n_customers": [n_total],
            "n_repeat": [n_rep],
            "repeat_rate": [n_rep / n_total if n_total else 0.0],
            "min_purchases_threshold": [min_purchases],
        })
        return PolarsResult(output=out)


step = RepeatPurchaseRateStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

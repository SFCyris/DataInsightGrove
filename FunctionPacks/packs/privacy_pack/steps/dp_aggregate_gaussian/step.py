"""dp_aggregate_gaussian — sum + Gaussian noise for (ε, δ)-DP."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class DpAggregateGaussianStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        v = params["valueColumn"]; g = params.get("groupColumn")
        eps = float(params.get("epsilon", 1.0))
        delta = float(params.get("delta", 1e-5))
        sens = float(params["sensitivity"])
        seed = int(params.get("seed", 42))
        # Gaussian mechanism stddev (analytic Gaussian — simplified).
        sigma = sens * math.sqrt(2 * math.log(1.25 / max(delta, 1e-12))) / eps
        rng = np.random.default_rng(seed)
        if g and g in df.columns:
            agg = df.group_by(g).agg(pl.col(v).sum().alias("__true_sum"))
            noise = rng.normal(0, sigma, size=agg.height)
            agg = agg.with_columns(
                (pl.col("__true_sum") + pl.Series("__noise", noise.tolist())).alias("dp_sum")
            ).drop("__noise" if "__noise" in agg.columns else [])
            return PolarsResult(output=agg)
        true_sum = float(df[v].sum() or 0)
        out = pl.DataFrame([{
            "true_sum": true_sum,
            "dp_sum": true_sum + float(rng.normal(0, sigma)),
            "epsilon": eps, "delta": delta, "sensitivity": sens, "noise_sigma": sigma,
        }])
        return PolarsResult(output=out)


step = DpAggregateGaussianStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

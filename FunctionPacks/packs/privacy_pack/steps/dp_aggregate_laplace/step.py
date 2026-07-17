"""dp_aggregate_laplace — sum + Laplace noise for ε-DP."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class DpAggregateLaplaceStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        v = params["valueColumn"]; g = params.get("groupColumn")
        eps = float(params.get("epsilon", 1.0))
        sens = float(params["sensitivity"])
        seed = int(params.get("seed", 42))
        scale = sens / eps
        rng = np.random.default_rng(seed)
        if g and g in df.columns:
            agg = df.group_by(g).agg(pl.col(v).sum().alias("__true_sum"))
            noise = rng.laplace(0, scale, size=agg.height)
            agg = agg.with_columns(
                (pl.col("__true_sum") + pl.Series("__noise", noise.tolist())).alias("dp_sum")
            ).drop("__noise" if "__noise" in agg.columns else [])
            agg = agg.with_columns([
                pl.lit(eps).alias("epsilon"),
                pl.lit(sens).alias("sensitivity"),
            ])
            return PolarsResult(output=agg)
        true_sum = float(df[v].sum() or 0)
        out = pl.DataFrame([{
            "true_sum": true_sum,
            "dp_sum": true_sum + float(rng.laplace(0, scale)),
            "epsilon": eps, "sensitivity": sens, "noise_scale": scale,
        }])
        return PolarsResult(output=out)


step = DpAggregateLaplaceStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

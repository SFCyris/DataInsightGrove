"""best_bayesian_ab — posterior P(best) per variant, Beta-Binomial."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class BestBayesianAbStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        v = params["variantColumn"]; c = params["convertedColumn"]
        n_samples = int(params.get("samples", 50000))
        seed = int(params.get("seed", 42))
        rng = np.random.default_rng(seed)
        # Per variant: successes + trials.
        agg = df.group_by(v).agg([
            pl.col(c).cast(pl.Int64).sum().alias("__success"),
            pl.col(c).count().alias("__trials"),
        ])
        variants = [str(x) for x in agg[v].to_list()]
        succ = np.asarray(agg["__success"].to_list(), dtype=int)
        tri = np.asarray(agg["__trials"].to_list(), dtype=int)
        # Sample from Beta(1+s, 1+t-s) posteriors.
        samples = np.column_stack([
            rng.beta(1 + s, 1 + t - s, size=n_samples) for s, t in zip(succ, tri)
        ])
        argmax = samples.argmax(axis=1)
        prob_best = np.bincount(argmax, minlength=len(variants)) / n_samples
        rows = [
            {"variant": variants[i],
             "n_trials": int(tri[i]), "n_successes": int(succ[i]),
             "observed_rate": float(succ[i] / tri[i]) if tri[i] else 0.0,
             "prob_best": float(prob_best[i])}
            for i in range(len(variants))
        ]
        out = pl.DataFrame(rows).sort("prob_best", descending=True)
        return PolarsResult(output=out)


step = BestBayesianAbStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

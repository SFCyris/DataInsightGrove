"""mcmc_pymc — general-case MCMC posterior summary."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class McmcPymcStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        try:
            import pymc as pm
            import arviz as az
            import numpy as np
        except ImportError as e:
            raise ImportError(
                "mcmc_pymc requires pymc + arviz. The pack does NOT auto-install "
                "pymc by default — see FunctionPacks/packs/bayesian_pack/INTERNAL_NOTES.md "
                "for install guidance."
            ) from e
        df = inputs["in"]
        v = params["valueColumn"]
        draws = int(params.get("draws", 1000))
        chains = int(params.get("chains", 2))
        values = np.asarray(df[v].drop_nulls().to_list(), dtype=float)
        with pm.Model():
            mu = pm.Normal("mu", mu=values.mean(), sigma=values.std() * 10)
            sigma = pm.HalfNormal("sigma", sigma=values.std() * 10)
            pm.Normal("obs", mu=mu, sigma=sigma, observed=values)
            trace = pm.sample(draws=draws, chains=chains, progressbar=False)
        summary = az.summary(trace).reset_index()
        rows = []
        for _, row in summary.iterrows():
            rows.append({
                "parameter": str(row["index"]),
                "posterior_mean": float(row["mean"]),
                "posterior_std": float(row["sd"]),
                "hdi_3_pct": float(row["hdi_3%"]),
                "hdi_97_pct": float(row["hdi_97%"]),
                "r_hat": float(row.get("r_hat", float("nan"))),
            })
        return PolarsResult(output=pl.DataFrame(rows))


step = McmcPymcStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

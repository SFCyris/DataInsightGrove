"""conjugate_normal — Normal-Normal posterior for the mean."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ConjugateNormalStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from scipy import stats
        df = inputs["in"]
        v = params["valueColumn"]
        g = params.get("groupColumn")
        mu0 = float(params.get("priorMean", 0.0))
        var0 = float(params.get("priorVariance", 100.0))
        var_lik = float(params.get("likelihoodVariance", 1.0))

        def _post(values):
            n = len(values)
            ybar = sum(values) / n if n else 0
            tau0 = 1 / var0; tau_lik = n / var_lik
            tau_post = tau0 + tau_lik
            mu_post = (tau0 * mu0 + tau_lik * ybar) / tau_post
            var_post = 1 / tau_post
            sd = math.sqrt(var_post)
            return mu_post, var_post, mu_post - 1.96 * sd, mu_post + 1.96 * sd

        rows = []
        if g and g in df.columns:
            for grp_val, sub in df.group_by(g, maintain_order=True):
                vals = sub[v].drop_nulls().to_list()
                mp, vp, lo, hi = _post(vals)
                rows.append({
                    "group": str(grp_val[0] if isinstance(grp_val, tuple) else grp_val),
                    "n": len(vals), "posterior_mean": mp,
                    "posterior_variance": vp,
                    "ci_lower_95": lo, "ci_upper_95": hi,
                })
        else:
            vals = df[v].drop_nulls().to_list()
            mp, vp, lo, hi = _post(vals)
            rows.append({
                "n": len(vals), "posterior_mean": mp, "posterior_variance": vp,
                "ci_lower_95": lo, "ci_upper_95": hi,
            })
        return PolarsResult(output=pl.DataFrame(rows))


step = ConjugateNormalStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

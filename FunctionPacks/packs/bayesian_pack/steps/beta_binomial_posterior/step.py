"""beta_binomial_posterior — conjugate Beta-Binomial closed-form posterior."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class BetaBinomialPosteriorStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from scipy import stats
        df = inputs["in"]
        g = params["groupColumn"]; s = params["successColumn"]; n = params["trialsColumn"]
        a0 = float(params.get("priorAlpha", 1.0)); b0 = float(params.get("priorBeta", 1.0))
        rows = []
        for grp_val, sub in df.group_by(g, maintain_order=True):
            successes = int(sub[s].sum() or 0)
            trials = int(sub[n].sum() or 0)
            a_post = a0 + successes; b_post = b0 + trials - successes
            mean = a_post / (a_post + b_post)
            lo, hi = stats.beta.ppf([0.025, 0.975], a_post, b_post)
            rows.append({
                "group": str(grp_val[0] if isinstance(grp_val, tuple) else grp_val),
                "trials": trials, "successes": successes,
                "posterior_alpha": a_post, "posterior_beta": b_post,
                "posterior_mean": float(mean),
                "ci_lower_95": float(lo), "ci_upper_95": float(hi),
            })
        return PolarsResult(output=pl.DataFrame(rows))


step = BetaBinomialPosteriorStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

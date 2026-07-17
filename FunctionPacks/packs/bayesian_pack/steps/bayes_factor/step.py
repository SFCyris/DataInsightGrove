"""bayes_factor — BF for two binomial rate hypotheses."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class BayesFactorStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from scipy.stats import binom
        df = inputs["in"]
        s = params["successColumn"]; n = params["trialsColumn"]
        p0 = float(params["p0"]); p1 = float(params["p1"])
        successes = int(df[s].sum() or 0); trials = int(df[n].sum() or 0)
        log_p_h0 = binom.logpmf(successes, trials, p0)
        log_p_h1 = binom.logpmf(successes, trials, p1)
        bf_10 = math.exp(log_p_h1 - log_p_h0) if log_p_h0 > -float("inf") else float("inf")
        if bf_10 > 100: strength = "decisive for H1"
        elif bf_10 > 10: strength = "strong for H1"
        elif bf_10 > 3: strength = "moderate for H1"
        elif bf_10 > 1: strength = "weak for H1"
        elif bf_10 > 1/3: strength = "weak for H0"
        elif bf_10 > 1/10: strength = "moderate for H0"
        else: strength = "strong for H0"
        out = pl.DataFrame([{
            "successes": successes, "trials": trials,
            "p0": p0, "p1": p1,
            "log_p_data_h0": float(log_p_h0), "log_p_data_h1": float(log_p_h1),
            "bayes_factor_10": float(bf_10),
            "evidence": strength,
        }])
        return PolarsResult(output=out)


step = BayesFactorStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

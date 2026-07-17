"""sequential_sprt — Wald SPRT trace + first-crossing decision."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SequentialSprtStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        c = params["convertedColumn"]; o = params["orderColumn"]
        p0 = float(params["p0"]); p1 = float(params["p1"])
        alpha = float(params.get("alpha", 0.05))
        beta = float(params.get("beta", 0.2))
        # Wald boundaries.
        upper = math.log((1 - beta) / alpha)
        lower = math.log(beta / (1 - alpha))
        sub = df.sort(o)
        log_lik = 0.0
        decision = "continue"
        rows = []
        for i, x in enumerate(sub[c].to_list(), start=1):
            xb = 1 if x else 0
            # Per-step LLR.
            if xb:
                log_lik += math.log(p1 / p0) if p0 > 0 else 0
            else:
                log_lik += math.log((1 - p1) / (1 - p0)) if p0 < 1 else 0
            if log_lik >= upper and decision == "continue":
                decision = "accept_H1"
            elif log_lik <= lower and decision == "continue":
                decision = "accept_H0"
            rows.append({"step": i, "log_likelihood_ratio": log_lik, "decision": decision})
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "SPRT decision",
            "data": {"final_decision": rows[-1]["decision"] if rows else "no_data",
                     "upper_bound": upper, "lower_bound": lower,
                     "n_observations": len(rows)},
        }])


step = SequentialSprtStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""step_funnel — distinct users at each ordered step."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class StepFunnelStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; e = params["eventColumn"]
        steps = [s.strip() for s in params["funnelSteps"].split(",") if s.strip()]
        if not steps:
            raise ValueError("step_funnel: funnelSteps required")
        # For ordered funnel, each step's users must include having done the prior step.
        prev_users = set(df[u].to_list())
        rows = []
        first_users = None
        for s in steps:
            step_users = set(df.filter(pl.col(e) == s)[u].to_list()) & prev_users
            if first_users is None:
                first_users = step_users
            rows.append({
                "step": s,
                "users": len(step_users),
                "conversion_from_first": len(step_users) / len(first_users) if first_users else 0.0,
            })
            prev_users = step_users
        return PolarsResult(output=pl.DataFrame(rows))


step = StepFunnelStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

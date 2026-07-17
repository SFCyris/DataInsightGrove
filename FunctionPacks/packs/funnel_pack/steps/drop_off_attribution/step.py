"""drop_off_attribution — per-step-pair drop-off counts + rates."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class DropOffAttributionStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; e = params["eventColumn"]
        steps = [s.strip() for s in params["funnelSteps"].split(",") if s.strip()]
        # Successive set-difference between step user sets.
        prev_users = set(df[u].to_list())
        rows = []
        for s in steps:
            step_users = set(df.filter(pl.col(e) == s)[u].to_list()) & prev_users
            lost = len(prev_users) - len(step_users)
            rate = lost / len(prev_users) if prev_users else 0.0
            rows.append({
                "step": s, "users_at_step": len(step_users),
                "users_dropped_entering": lost, "drop_rate_entering": rate,
            })
            prev_users = step_users
        return PolarsResult(output=pl.DataFrame(rows))


step = DropOffAttributionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

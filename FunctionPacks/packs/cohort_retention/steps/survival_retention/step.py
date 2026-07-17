"""survival_retention — Kaplan-Meier estimator on tenure + event."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class SurvivalRetentionStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        t = params["tenureColumn"]; e = params["eventColumn"]
        clean = df.drop_nulls(subset=[t, e])
        tenures = np.asarray(clean[t].to_list(), dtype=float)
        events = np.asarray([1 if v else 0 for v in clean[e].to_list()], dtype=int)
        # KM estimator.
        unique_times = sorted(set(int(x) for x in tenures))
        n_at_risk = len(tenures)
        survival = 1.0
        rows = []
        for tt in unique_times:
            mask = tenures == tt
            d = int(events[mask].sum())  # deaths/churns at time tt
            n = n_at_risk
            if n > 0:
                survival *= (1 - d / n)
            rows.append({"day": tt, "n_at_risk": n, "events": d, "survival_prob": float(survival)})
            n_at_risk -= int(mask.sum())
        return PolarsResult(output=pl.DataFrame(rows))


step = SurvivalRetentionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

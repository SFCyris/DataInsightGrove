"""synthetic_control — minimise pre-treatment fit to construct synthetic counterfactual."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class SyntheticControlStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from scipy.optimize import minimize
        df = inputs["in"]
        u = params["unitColumn"]; tcol = params["timeColumn"]; y = params["outcomeColumn"]
        treated_unit = params["treatedUnit"]
        treatment_time = float(params["treatmentTime"])
        # Pivot: rows = time, columns = unit, value = outcome.
        wide = df.pivot(values=y, index=tcol, on=u, aggregate_function="first").sort(tcol)
        if treated_unit not in wide.columns:
            raise ValueError(f"synthetic_control: treated unit {treated_unit!r} not in data")
        times = np.asarray(wide[tcol].to_list(), dtype=float)
        treated = np.asarray(wide[treated_unit].to_list(), dtype=float)
        donors = [c for c in wide.columns if c not in (tcol, treated_unit)]
        donor_mat = wide.select(donors).to_numpy().astype(float)

        pre_mask = times < treatment_time
        if pre_mask.sum() < 2:
            raise ValueError("synthetic_control: not enough pre-treatment periods")

        def _loss(w):
            synth = donor_mat @ w
            return float(np.sum((treated[pre_mask] - synth[pre_mask]) ** 2))

        n_donors = donor_mat.shape[1]
        x0 = np.full(n_donors, 1.0 / n_donors)
        constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        bounds = [(0.0, 1.0)] * n_donors
        result = minimize(_loss, x0, bounds=bounds, constraints=constraints, method="SLSQP")
        weights = result.x
        synth = donor_mat @ weights
        rows = []
        for i, t in enumerate(times):
            rows.append({
                "period": float(t),
                "treated": float(treated[i]),
                "synthetic": float(synth[i]),
                "effect": float(treated[i] - synth[i]),
                "is_post_treatment": bool(t >= treatment_time),
            })
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "Synthetic control",
            "data": {"donor_weights": dict(zip(donors, [float(w) for w in weights])),
                      "treatment_time": treatment_time,
                      "treated_unit": treated_unit,
                      "average_post_effect": float(np.mean([r["effect"] for r in rows if r["is_post_treatment"]]))},
        }])


step = SyntheticControlStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

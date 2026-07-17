"""sample_size_calc — required N per arm for two-sample proportion test."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SampleSizeCalcStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from scipy import stats
        baseline = float(params["baselineRate"])
        mde = float(params["mde"])
        alpha = float(params.get("alpha", 0.05))
        power = float(params.get("power", 0.8))
        treatment = baseline + mde
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = stats.norm.ppf(power)
        p_pooled = (baseline + treatment) / 2
        # Standard formula for two-sample proportion test.
        numerator = (z_alpha * math.sqrt(2 * p_pooled * (1 - p_pooled)) +
                       z_beta * math.sqrt(baseline * (1 - baseline) + treatment * (1 - treatment))) ** 2
        denominator = mde ** 2
        n_per_arm = math.ceil(numerator / denominator) if denominator > 0 else 0
        out = pl.DataFrame([{
            "baseline_rate": baseline, "treatment_rate": treatment, "mde": mde,
            "alpha": alpha, "power": power,
            "n_per_arm": n_per_arm, "n_total": n_per_arm * 2,
        }])
        return PolarsResult(output=out)


step = SampleSizeCalcStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

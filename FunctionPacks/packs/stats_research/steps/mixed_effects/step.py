"""mixed_effects — statsmodels MixedLM (random intercept + fixed effects)."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class MixedEffectsStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import statsmodels.formula.api as smf
        df = inputs["in"]
        target = params["targetColumn"]; features = params.get("featureColumns") or []
        group = params["groupColumn"]
        clean = df.drop_nulls(subset=[target, group, *features]).to_pandas()
        # Build R-style formula.
        formula = f"{target} ~ " + " + ".join(features) if features else f"{target} ~ 1"
        model = smf.mixedlm(formula, data=clean, groups=clean[group]).fit()
        rows = []
        for name in model.params.index:
            try:
                rows.append({
                    "term": str(name),
                    "estimate": float(model.params[name]),
                    "std_error": float(model.bse[name]) if name in model.bse else None,
                    "z_value": float(model.tvalues[name]) if name in model.tvalues else None,
                    "p_value": float(model.pvalues[name]) if name in model.pvalues else None,
                })
            except Exception:
                continue
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "Mixed-effects fit",
            "data": {"n_obs": int(model.nobs),
                      "log_likelihood": float(model.llf),
                      "n_groups": int(clean[group].nunique())},
        }])


step = MixedEffectsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

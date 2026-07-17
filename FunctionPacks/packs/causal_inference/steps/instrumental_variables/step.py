"""instrumental_variables — manual 2SLS via OLS twice."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class InstrumentalVariablesStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import statsmodels.api as sm
        df = inputs["in"]
        y = params["outcomeColumn"]; endog = params["endogenousColumn"]
        instruments = params.get("instrumentColumns") or []
        ctrls = params.get("controlColumns") or []
        keep = [y, endog, *instruments, *ctrls]
        clean = df.drop_nulls(subset=keep).select(keep).to_pandas()
        # Stage 1: predict endogenous from instruments + controls.
        X1 = sm.add_constant(clean[[*instruments, *ctrls]].astype(float))
        first_stage = sm.OLS(clean[endog].astype(float), X1).fit()
        endog_hat = first_stage.fittedvalues
        # Stage 2: outcome ~ endog_hat + controls.
        X2_data = clean[ctrls].copy() if ctrls else clean[[]].copy()
        X2_data["__endog_hat"] = endog_hat
        X2 = sm.add_constant(X2_data.astype(float))
        second_stage = sm.OLS(clean[y].astype(float), X2).fit()
        rows = []
        for term in second_stage.params.index:
            label = "iv_estimate" if term == "__endog_hat" else str(term)
            rows.append({
                "term": label,
                "estimate": float(second_stage.params[term]),
                "std_error": float(second_stage.bse[term]),
                "t_value": float(second_stage.tvalues[term]),
                "p_value": float(second_stage.pvalues[term]),
            })
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "Instrumental Variables (2SLS)",
            "data": {"first_stage_r_squared": float(first_stage.rsquared),
                      "second_stage_r_squared": float(second_stage.rsquared),
                      "n_obs": int(second_stage.nobs),
                      "instruments": instruments},
        }])


step = InstrumentalVariablesStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

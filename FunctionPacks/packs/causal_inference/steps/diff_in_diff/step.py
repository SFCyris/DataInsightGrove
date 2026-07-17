"""diff_in_diff — DiD via OLS interaction term."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class DiffInDiffStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import statsmodels.formula.api as smf
        df = inputs["in"]
        y = params["outcomeColumn"]; t = params["treatedColumn"]; p = params["postColumn"]
        ctrls = params.get("controlColumns") or []
        keep = [y, t, p, *ctrls]
        clean = df.drop_nulls(subset=keep).select(keep).to_pandas()
        formula = f"{y} ~ {t} * {p}"
        if ctrls:
            formula += " + " + " + ".join(ctrls)
        model = smf.ols(formula, data=clean).fit()
        rows = []
        for term in model.params.index:
            rows.append({
                "term": str(term),
                "estimate": float(model.params[term]),
                "std_error": float(model.bse[term]),
                "t_value": float(model.tvalues[term]),
                "p_value": float(model.pvalues[term]),
                "is_did_interaction": ":" in str(term) and t in str(term) and p in str(term),
            })
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "Difference-in-differences",
            "data": {"n_obs": int(model.nobs),
                      "r_squared": float(model.rsquared),
                      "did_term": f"{t}:{p}"},
        }])


step = DiffInDiffStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

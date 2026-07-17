"""glm_probit — statsmodels GLM with probit link."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class GlmProbitStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import statsmodels.api as sm
        df = inputs["in"]
        target = params["targetColumn"]; features = params.get("featureColumns") or []
        clean = df.drop_nulls(subset=[target, *features])
        y = np.asarray(clean[target].to_list(), dtype=float)
        X = sm.add_constant(clean.select(features).to_pandas().astype(float))
        model = sm.GLM(y, X, family=sm.families.Binomial(link=sm.families.links.probit())).fit()
        rows = [{
            "term": n,
            "estimate": float(model.params[n]), "std_error": float(model.bse[n]),
            "z_value": float(model.tvalues[n]), "p_value": float(model.pvalues[n]),
            "ci_lower": float(model.conf_int().loc[n, 0]),
            "ci_upper": float(model.conf_int().loc[n, 1]),
        } for n in X.columns]
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "GLM Probit fit",
            "data": {"n_obs": int(model.nobs), "deviance": float(model.deviance), "aic": float(model.aic)},
        }])


step = GlmProbitStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

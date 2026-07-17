"""glm_poisson — statsmodels Poisson regression for counts."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class GlmPoissonStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import statsmodels.api as sm
        df = inputs["in"]
        target = params["targetColumn"]; features = params.get("featureColumns") or []
        clean = df.drop_nulls(subset=[target, *features])
        y = np.asarray(clean[target].to_list(), dtype=float)
        X = sm.add_constant(clean.select(features).to_pandas().astype(float))
        model = sm.GLM(y, X, family=sm.families.Poisson()).fit()
        rows = [{
            "term": n,
            "estimate": float(model.params[n]),
            "incidence_rate_ratio": float(np.exp(model.params[n])),
            "std_error": float(model.bse[n]),
            "z_value": float(model.tvalues[n]), "p_value": float(model.pvalues[n]),
        } for n in X.columns]
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "GLM Poisson fit",
            "data": {"n_obs": int(model.nobs), "deviance": float(model.deviance), "aic": float(model.aic)},
        }])


step = GlmPoissonStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

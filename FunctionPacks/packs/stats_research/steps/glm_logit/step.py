"""glm_logit — statsmodels Logit, research-flavored coefficient table."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


def _glm(family_name: str, df, params):
    import statsmodels.api as sm
    import numpy as np
    target = params["targetColumn"]; features = params.get("featureColumns") or []
    clean = df.drop_nulls(subset=[target, *features])
    y = np.asarray(clean[target].to_list(), dtype=float)
    X = clean.select(features).to_pandas().astype(float)
    X = sm.add_constant(X)
    family = {"logit": sm.families.Binomial(),
              "probit": sm.families.Binomial(link=sm.families.links.probit()),
              "poisson": sm.families.Poisson()}[family_name]
    model = sm.GLM(y, X, family=family).fit()
    rows = []
    for name in X.columns:
        rows.append({
            "term": name,
            "estimate": float(model.params[name]),
            "std_error": float(model.bse[name]),
            "z_value": float(model.tvalues[name]),
            "p_value": float(model.pvalues[name]),
            "ci_lower": float(model.conf_int().loc[name, 0]),
            "ci_upper": float(model.conf_int().loc[name, 1]),
        })
    return pl.DataFrame(rows), {
        "model": f"GLM-{family_name}",
        "n_obs": int(model.nobs),
        "deviance": float(model.deviance),
        "aic": float(model.aic),
    }


class GlmLogitStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df, summary = _glm("logit", inputs["in"], params)
        return PolarsResult(output=df, artifacts=[{
            "kind": "metrics", "label": "GLM Logit fit", "data": summary,
        }])


step = GlmLogitStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

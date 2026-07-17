"""bayesian_regression — closed-form Bayesian ridge."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class BayesianRegressionStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from sklearn.linear_model import BayesianRidge
        df = inputs["in"]
        y = params["targetColumn"]; features = params.get("featureColumns") or []
        prior_prec = float(params.get("priorPrecision", 1.0))
        clean = df.drop_nulls(subset=[y, *features])
        X = clean.select(features).to_numpy().astype(float)
        y_arr = np.asarray(clean[y].to_list(), dtype=float)
        # BayesianRidge: alpha_init = noise precision, lambda_init = coef precision.
        model = BayesianRidge(lambda_init=prior_prec).fit(X, y_arr)
        # Posterior std per coef approximated by sqrt(diag(sigma_)).
        try:
            std = np.sqrt(np.diag(model.sigma_))
        except Exception:
            std = np.zeros_like(model.coef_)
        rows = [{"term": "(intercept)", "posterior_mean": float(model.intercept_),
                  "posterior_std": None, "ci_lower_95": None, "ci_upper_95": None}]
        for name, coef, s in zip(features, model.coef_, std):
            lo = float(coef - 1.96 * s) if s > 0 else None
            hi = float(coef + 1.96 * s) if s > 0 else None
            rows.append({"term": name, "posterior_mean": float(coef),
                          "posterior_std": float(s),
                          "ci_lower_95": lo, "ci_upper_95": hi})
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "Bayesian regression",
            "data": {"n_obs": int(X.shape[0]),
                      "alpha_noise_precision": float(model.alpha_),
                      "lambda_coef_precision": float(model.lambda_)},
        }])


step = BayesianRegressionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

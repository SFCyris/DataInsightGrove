"""cox_proportional_hazards — lifelines Cox regression coefficient table."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class CoxPhStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from lifelines import CoxPHFitter
        df = inputs["in"]
        d = params["durationColumn"]; e = params["eventColumn"]
        features = params.get("featureColumns") or []
        keep = [d, e, *features]
        clean = df.drop_nulls(subset=keep).select(keep).to_pandas()
        cph = CoxPHFitter().fit(clean, duration_col=d, event_col=e)
        summary = cph.summary
        rows = []
        for term in summary.index:
            rows.append({
                "term": str(term),
                "coef": float(summary.loc[term, "coef"]),
                "hazard_ratio": float(summary.loc[term, "exp(coef)"]),
                "std_error": float(summary.loc[term, "se(coef)"]),
                "z_value": float(summary.loc[term, "z"]),
                "p_value": float(summary.loc[term, "p"]),
                "ci_lower": float(summary.loc[term, "exp(coef) lower 95%"]),
                "ci_upper": float(summary.loc[term, "exp(coef) upper 95%"]),
            })
        return PolarsResult(output=pl.DataFrame(rows), artifacts=[{
            "kind": "metrics", "label": "Cox PH fit",
            "data": {"n_obs": int(cph._n_examples),
                      "concordance": float(cph.concordance_index_),
                      "log_likelihood": float(cph.log_likelihood_)},
        }])


step = CoxPhStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

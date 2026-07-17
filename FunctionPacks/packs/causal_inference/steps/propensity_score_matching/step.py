"""propensity_score_matching — logistic-regression PS + 1:1 NN match."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class PropensityScoreMatchingStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from sklearn.linear_model import LogisticRegression
        df = inputs["in"]
        t = params["treatmentColumn"]
        covs = params.get("covariateColumns") or []
        caliper = float(params.get("caliper", 0.1))

        clean = df.drop_nulls(subset=[t, *covs]).with_row_index("__rownum")
        X = clean.select(covs).to_numpy().astype(float)
        y = np.asarray(clean[t].to_list(), dtype=int)
        ps = LogisticRegression(max_iter=500).fit(X, y).predict_proba(X)[:, 1]
        clean = clean.with_columns(pl.Series("propensity_score", ps))

        treated = clean.filter(pl.col(t) == 1)
        control = clean.filter(pl.col(t) == 0)
        ctrl_ps = np.asarray(control["propensity_score"].to_list(), dtype=float)
        ctrl_idx = np.asarray(control["__rownum"].to_list(), dtype=int)

        used = set()
        pairs = []
        for tps, tidx in zip(treated["propensity_score"].to_list(), treated["__rownum"].to_list()):
            distances = np.abs(ctrl_ps - tps)
            order = np.argsort(distances)
            for j in order:
                if int(ctrl_idx[j]) in used: continue
                if distances[j] > caliper: break
                used.add(int(ctrl_idx[j]))
                pairs.append((int(tidx), int(ctrl_idx[j])))
                break
        if not pairs:
            return PolarsResult(output=clean.head(0))
        treated_rows = clean.filter(pl.col("__rownum").is_in([p[0] for p in pairs])).with_columns(
            pl.lit("treated").alias("__match_role")
        )
        control_rows = clean.filter(pl.col("__rownum").is_in([p[1] for p in pairs])).with_columns(
            pl.lit("control").alias("__match_role")
        )
        out = pl.concat([treated_rows, control_rows]).drop("__rownum")
        return PolarsResult(output=out, artifacts=[{
            "kind": "metrics", "label": "PSM matching",
            "data": {"n_treated_total": int(treated.height),
                      "n_matched_pairs": len(pairs), "caliper": caliper},
        }])


step = PropensityScoreMatchingStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

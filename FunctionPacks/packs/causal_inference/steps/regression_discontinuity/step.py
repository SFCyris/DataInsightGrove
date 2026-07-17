"""regression_discontinuity — sharp RDD via local-linear fit on each side."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class RegressionDiscontinuityStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from sklearn.linear_model import LinearRegression
        df = inputs["in"]
        y = params["outcomeColumn"]; r = params["runningColumn"]
        cutoff = float(params["cutoff"])
        bw = params.get("bandwidth")
        clean = df.drop_nulls(subset=[y, r])
        if bw is not None:
            bw = float(bw)
            clean = clean.filter((pl.col(r) >= cutoff - bw) & (pl.col(r) <= cutoff + bw))
        run = np.asarray(clean[r].to_list(), dtype=float)
        out = np.asarray(clean[y].to_list(), dtype=float)
        # Centre around cutoff.
        run_c = run - cutoff
        left_mask = run_c < 0; right_mask = run_c >= 0
        intercept_left = intercept_right = float("nan")
        if left_mask.sum() >= 2:
            mleft = LinearRegression().fit(run_c[left_mask].reshape(-1, 1), out[left_mask])
            intercept_left = float(mleft.intercept_)
        if right_mask.sum() >= 2:
            mright = LinearRegression().fit(run_c[right_mask].reshape(-1, 1), out[right_mask])
            intercept_right = float(mright.intercept_)
        rdd_jump = intercept_right - intercept_left
        result = pl.DataFrame([{
            "cutoff": cutoff,
            "bandwidth": bw,
            "n_left": int(left_mask.sum()),
            "n_right": int(right_mask.sum()),
            "intercept_left": intercept_left,
            "intercept_right": intercept_right,
            "rdd_jump_estimate": rdd_jump,
        }])
        return PolarsResult(output=result)


step = RegressionDiscontinuityStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

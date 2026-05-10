from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ChangepointDetectionStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import numpy as np

        df = inputs["in"]
        col = params["value"]
        threshold = float(params.get("threshold", 5.0))

        x = df[col].to_numpy()
        n = len(x)
        if n < 10:
            raise ValueError(f"changepoint_detection: need ≥10 observations, got {n}")

        # Standardise so threshold is in σ units, ignoring NaN.
        mu = np.nanmean(x)
        sigma = np.nanstd(x)
        if sigma == 0:
            sigma = 1.0
        z = (x - mu) / sigma
        # Two-sided CUSUM statistic
        s_pos = np.zeros(n)
        s_neg = np.zeros(n)
        for i in range(1, n):
            xi = z[i] if not np.isnan(z[i]) else 0.0
            s_pos[i] = max(0.0, s_pos[i - 1] + xi - 0.5)
            s_neg[i] = min(0.0, s_neg[i - 1] + xi + 0.5)
        cusum = s_pos + s_neg
        is_cp = (s_pos > threshold) | (s_neg < -threshold)

        return PolarsResult(output=df.with_columns([
            pl.Series(name="cusum", values=cusum.tolist()),
            pl.Series(name="is_changepoint", values=is_cp.tolist()),
        ]))


step = ChangepointDetectionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

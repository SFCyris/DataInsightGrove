from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class KpssTestStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from statsmodels.tsa.stattools import kpss

        df = inputs["in"]
        col = params["value"]
        regression = params.get("regression", "c")
        x = df[col].drop_nulls().to_numpy()
        if len(x) < 12:
            raise ValueError(f"kpss_test: need ≥12 non-null observations, got {len(x)}")

        # statsmodels emits "InterpolationWarning" when p-value is at the
        # extremes of the table; that's expected, not an error.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stat, p, lags, crit = kpss(x, regression=regression, nlags="auto")

        out = pl.DataFrame([{
            "value_column": col,
            "n": int(len(x)),
            "lags_used": int(lags),
            "kpss_statistic": float(stat),
            "p_value": float(p),
            "critical_1pct": float(crit.get("1%", float("nan"))),
            "critical_5pct": float(crit.get("5%", float("nan"))),
            "critical_10pct": float(crit.get("10%", float("nan"))),
            "verdict": "non-stationary" if p < 0.05 else "stationary",
            "regression": regression,
        }])
        return PolarsResult(output=out)


step = KpssTestStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

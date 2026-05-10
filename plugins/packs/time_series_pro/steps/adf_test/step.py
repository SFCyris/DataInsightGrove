from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class AdfTestStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from statsmodels.tsa.stattools import adfuller

        df = inputs["in"]
        col = params["value"]
        regression = params.get("regression", "c")
        x = df[col].drop_nulls().to_numpy()
        if len(x) < 12:
            raise ValueError(f"adf_test: need ≥12 non-null observations, got {len(x)}")

        stat, p, lags, n_obs, crit, _ = adfuller(x, regression=regression, autolag="AIC")
        out = pl.DataFrame([{
            "value_column": col,
            "n": int(n_obs),
            "lags_used": int(lags),
            "adf_statistic": float(stat),
            "p_value": float(p),
            "critical_1pct": float(crit.get("1%", float("nan"))),
            "critical_5pct": float(crit.get("5%", float("nan"))),
            "critical_10pct": float(crit.get("10%", float("nan"))),
            "verdict": "stationary" if p < 0.05 else "non-stationary",
            "regression": regression,
        }])
        return PolarsResult(output=out)


step = AdfTestStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

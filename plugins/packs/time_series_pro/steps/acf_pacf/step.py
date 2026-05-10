from __future__ import annotations

import json
from math import sqrt
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class AcfPacfStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from statsmodels.tsa.stattools import acf, pacf

        df = inputs["in"]
        col = params["value"]
        max_lag = int(params.get("max_lag", 40))

        x = df[col].drop_nulls().to_numpy()
        if len(x) < max_lag + 5:
            raise ValueError(
                f"acf_pacf: need ≥{max_lag + 5} non-null observations, got {len(x)}",
            )

        acf_vals = acf(x, nlags=max_lag, fft=True)
        pacf_vals = pacf(x, nlags=max_lag, method="ywm")
        # 95% CI for white noise: ±1.96 / sqrt(n)
        bound = 1.96 / sqrt(len(x))

        rows: list[dict[str, Any]] = []
        for lag in range(max_lag + 1):
            rows.append({
                "lag": lag,
                "acf": float(acf_vals[lag]),
                "pacf": float(pacf_vals[lag]),
                "ci_upper": bound,
                "ci_lower": -bound,
                "significant_acf": abs(float(acf_vals[lag])) > bound and lag > 0,
                "significant_pacf": abs(float(pacf_vals[lag])) > bound and lag > 0,
            })
        return PolarsResult(output=pl.DataFrame(rows))


step = AcfPacfStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

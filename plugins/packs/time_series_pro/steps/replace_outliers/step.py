"""Replace outlier-flagged values with a rolling median.

Median (not mean) because mean would be pulled toward the very
outlier we're trying to remove. Median ignores outliers in its own
window — exactly the property we want for a robust replacement.

Pairs with `anomaly_zscore`: that step flags rows; this one cleans
them before forecasting so the trend / seasonality estimators don't
absorb the noise.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ReplaceOutliersStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        value_col = params["value"]
        flag_col = params["flag"]
        window = int(params.get("window", 7))
        out_col = str(params.get("output_column") or "value_clean")

        if value_col not in df.columns:
            raise ValueError(f"replace_outliers: value column {value_col!r} not found")
        if flag_col not in df.columns:
            raise ValueError(f"replace_outliers: flag column {flag_col!r} not found")

        # Compute rolling median on the original series. Polars
        # `rolling_median` already handles the warm-up via min_periods.
        # We use centered=False (trailing window) so the cleaned series
        # is causal — same convention the forecast step expects.
        cleaned = (
            pl.when(pl.col(flag_col))
            .then(pl.col(value_col).rolling_median(window_size=window, min_periods=2))
            .otherwise(pl.col(value_col))
        ).alias(out_col)
        return PolarsResult(output=df.with_columns(cleaned))


step = ReplaceOutliersStep(
    json.loads((Path(__file__).parent / "manifest.json").read_text())
)

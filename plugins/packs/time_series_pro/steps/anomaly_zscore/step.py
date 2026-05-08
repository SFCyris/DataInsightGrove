"""Rolling-window z-score anomaly detector.

Why rolling instead of global: in real time-series the mean drifts
(seasonality, trend, regime changes). A global z-score over a year
of sales would flag every December's spike as an "anomaly" even
though those spikes are normal. A rolling z-score asks "is this
point unusual *relative to its recent neighbourhood*" — robust to
drift, surfaces what humans actually consider anomalous.

Doesn't drop rows: the boolean ``is_anomaly`` column lets downstream
steps decide. ``replace_outliers`` smooths them, ``filter_rows``
keeps only the alerts, ``export_to_image`` renders them on the
chart in red.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class AnomalyZscoreStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        col = params["value"]
        window = int(params.get("window", 30))
        threshold = float(params.get("threshold", 3.0))
        min_periods = int(params.get("min_periods", 10))

        if col not in df.columns:
            raise ValueError(f"anomaly_zscore: column {col!r} not found")
        n = df.height
        if n < min_periods:
            raise ValueError(
                f"anomaly_zscore: need ≥{min_periods} rows, got {n}"
            )

        # Rolling mean + std with min_periods so the head of the
        # series doesn't produce flapping z-scores while stats
        # stabilize. Polars' rolling functions emit null for the
        # warm-up window — we treat those as "not anomalous yet".
        out = df.with_columns([
            (
                (pl.col(col) - pl.col(col).rolling_mean(
                    window_size=window, min_periods=min_periods
                ))
                / pl.col(col).rolling_std(
                    window_size=window, min_periods=min_periods
                ).clip(lower_bound=1e-9)
            ).alias("zscore"),
        ]).with_columns([
            (pl.col("zscore").abs() > threshold)
            .fill_null(False)
            .alias("is_anomaly"),
        ])
        return PolarsResult(output=out)


step = AnomalyZscoreStep(
    json.loads((Path(__file__).parent / "manifest.json").read_text())
)

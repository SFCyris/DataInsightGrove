from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class OutliersIqrStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import numpy as np

        df = inputs["in"]
        col = params["value"]
        k = float(params.get("k", 1.5))
        out_col = params.get("output_column", "is_outlier")

        x = df[col].drop_nulls().to_numpy()
        if len(x) < 4:
            raise ValueError(f"outliers_iqr: need ≥4 non-null observations, got {len(x)}")

        q1, q3 = float(np.percentile(x, 25)), float(np.percentile(x, 75))
        iqr = q3 - q1
        lower, upper = q1 - k * iqr, q3 + k * iqr

        flagged = df.with_columns(
            pl.when(pl.col(col).is_null())
              .then(False)
              .otherwise((pl.col(col) < lower) | (pl.col(col) > upper))
              .alias(out_col),
        )
        return PolarsResult(output=flagged)


step = OutliersIqrStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""Z-score (standardization) step.

Adds (col - mean) / std as a new column. Worked example from
docs/AUTHORING_GUIDE.md (Tutorial 2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ZScoreStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        col = params["column"]
        out_col = params.get("output_column") or "z_score"

        if col not in df.columns:
            raise ValueError(f"zscore: column '{col}' not found")

        series = df.get_column(col).cast(pl.Float64)
        mean = series.mean()
        std = series.std()

        if std is None or std == 0:
            zscores = pl.Series(out_col, [0.0] * df.height)
        else:
            zscores = ((series - mean) / std).rename(out_col)

        out = df.with_columns(zscores)
        return PolarsResult(output=out)


step = ZScoreStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

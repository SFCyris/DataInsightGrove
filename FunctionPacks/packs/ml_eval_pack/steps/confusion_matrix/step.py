from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ConfusionMatrixStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        a, p = params["actual"], params["predicted"]
        clean = df.select([a, p]).drop_nulls()

        counts = (
            clean.group_by([a, p])
                 .agg(pl.len().alias("count"))
                 .rename({a: "actual", p: "predicted"})
                 .sort(["actual", "predicted"])
        )
        # Row-normalised rate (precision-style: per-actual class)
        per_actual = counts.group_by("actual").agg(pl.col("count").sum().alias("actual_total"))
        out = (
            counts.join(per_actual, on="actual", how="left")
                  .with_columns((pl.col("count") / pl.col("actual_total")).alias("rate"))
                  .select(["actual", "predicted", "count", "rate"])
        )
        return PolarsResult(output=out)


step = ConfusionMatrixStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

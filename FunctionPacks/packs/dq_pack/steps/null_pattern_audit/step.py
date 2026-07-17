from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class NullPatternAuditStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        top_n = int(params.get("top_n", 10))
        if df.height == 0:
            raise ValueError("null_pattern_audit: empty input")

        cols = df.columns
        # For each row, build a sorted-tuple of column names that are null.
        null_mask = df.select([pl.col(c).is_null().alias(c) for c in cols])
        null_lists: list[str] = []
        for row in null_mask.iter_rows():
            null_cols = sorted(c for c, is_null in zip(cols, row) if is_null)
            null_lists.append(", ".join(null_cols) if null_cols else "(no nulls)")

        pattern_counts = pl.DataFrame({"null_pattern": null_lists})
        result = (
            pattern_counts.group_by("null_pattern")
                          .agg(pl.len().alias("count"))
                          .sort("count", descending=True)
                          .head(top_n)
                          .with_columns(
                              (pl.col("count") / df.height).alias("fraction"),
                              pl.col("null_pattern").str.split(", ").list.len().alias("n_nulls_in_row"),
                          )
        )
        return PolarsResult(output=result)


step = NullPatternAuditStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

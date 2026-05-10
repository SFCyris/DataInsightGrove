from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


_TRUNCATE_FREQ = {"week": "1w", "month": "1mo", "quarter": "1q", "year": "1y"}
_OFFSET = {"week": "1w", "month": "1mo", "quarter": "1q", "year": "1y"}


class DateSnapStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        col = params["date_column"]
        period = params.get("period", "week")
        boundary = params.get("boundary", "start")
        out_col = params.get("output_column", "snapped_date")

        if period not in _TRUNCATE_FREQ:
            raise ValueError(f"date_snap: unknown period {period!r}")

        # Polars dt.truncate snaps DOWN to the period start.
        snapped = pl.col(col).dt.truncate(_TRUNCATE_FREQ[period])
        if boundary == "end":
            # End-of-period = next-period-start - 1 day
            snapped = snapped.dt.offset_by(_OFFSET[period]).dt.offset_by("-1d")

        return PolarsResult(output=df.with_columns(snapped.alias(out_col)))


step = DateSnapStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

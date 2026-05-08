from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class FiscalYearPartsStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        col = params["date_column"]
        start_month = int(params.get("fy_start_month", 1))
        prefix = params.get("prefix", "fy_")

        # Fiscal year = calendar year of (date + (12 - start_month + 1) months)?
        # Simpler: a date's FY year is its calendar year if its month >= start_month;
        # else calendar year - 1. (When start=1 this yields the calendar year.)
        # Wait — that's the convention "FY ends in month start_month-1" used in the
        # US federal case (FY26 starts Oct 2025, ends Sep 2026; we'd label Jan 2026
        # as FY26, which is calendar year + 1 when month < start). Let's adopt that:
        #   if month >= start_month: fy = calendar_year + 1
        #   else:                    fy = calendar_year
        # Special-case start=1: month >= 1 is always true → fy = year + 1, which is
        # wrong for the calendar case. So when start=1, fy = calendar_year directly.

        if start_month == 1:
            fy_year_expr = pl.col(col).dt.year()
        else:
            fy_year_expr = (
                pl.when(pl.col(col).dt.month() >= start_month)
                  .then(pl.col(col).dt.year() + 1)
                  .otherwise(pl.col(col).dt.year())
            )

        # Fiscal month: 1..12 starting at start_month.
        # = ((calendar_month - start_month) mod 12) + 1
        fy_month_expr = ((pl.col(col).dt.month() - start_month) % 12) + 1
        fy_quarter_expr = ((fy_month_expr - 1) // 3) + 1

        return PolarsResult(output=df.with_columns([
            fy_year_expr.alias(f"{prefix}year"),
            fy_quarter_expr.alias(f"{prefix}quarter"),
            fy_month_expr.alias(f"{prefix}month"),
        ]))


step = FiscalYearPartsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _bdays(start: date | None, end: date | None, holiday_set: set[date]) -> int | None:
    if start is None or end is None:
        return None
    if start > end:
        start, end = end, start
    cur = start
    count = 0
    while cur <= end:
        if cur.weekday() < 5 and cur not in holiday_set:
            count += 1
        cur += timedelta(days=1)
    return count


class BusinessDaysBetweenStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import holidays as _hols

        df = inputs["in"]
        start_col = params["start_column"]
        end_col = params["end_column"]
        country = params.get("country", "US")
        out_col = params.get("output_column", "bdays")

        # Build a country-specific holiday set spanning the data's date range.
        # python-holidays takes a `years` iterable.
        starts = df[start_col].drop_nulls().to_list()
        ends = df[end_col].drop_nulls().to_list()
        if not starts or not ends:
            return PolarsResult(output=df.with_columns(pl.lit(None).alias(out_col)))
        # `holidays` returns dates; coerce datetimes to date for set membership
        all_dates = [d.date() if hasattr(d, "date") else d for d in starts + ends]
        years = range(min(d.year for d in all_dates), max(d.year for d in all_dates) + 2)
        try:
            holiday_set: set[date] = set(_hols.country_holidays(country, years=years).keys())
        except Exception:
            holiday_set = set()

        # Polars per-row map
        starts_list = df[start_col].to_list()
        ends_list = df[end_col].to_list()
        results: list[int | None] = []
        for s, e in zip(starts_list, ends_list):
            s_date = s.date() if hasattr(s, "date") else s
            e_date = e.date() if hasattr(e, "date") else e
            results.append(_bdays(s_date, e_date, holiday_set))

        return PolarsResult(output=df.with_columns(pl.Series(name=out_col, values=results)))


step = BusinessDaysBetweenStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

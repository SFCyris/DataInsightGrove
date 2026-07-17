from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


_AVAILABLE = available_timezones()


def _resolve(raw: Any) -> tuple[bool, str | None, int | None]:
    if raw is None:
        return (False, None, None)
    s = str(raw).strip()
    if not s or s not in _AVAILABLE:
        return (False, None, None)
    try:
        z = ZoneInfo(s)
    except ZoneInfoNotFoundError:
        return (False, None, None)
    now = datetime.now(z)
    offset = now.utcoffset()
    minutes = int(offset.total_seconds() / 60) if offset is not None else None
    return (True, s, minutes)


class TimezoneResolveStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        col = params["timezone_column"]

        valid: list[bool] = []
        canonical: list[str | None] = []
        offset: list[int | None] = []
        for raw in df[col].to_list():
            v, c, o = _resolve(raw)
            valid.append(v); canonical.append(c); offset.append(o)

        return PolarsResult(output=df.with_columns([
            pl.Series(name="timezone_valid", values=valid),
            pl.Series(name="timezone_canonical", values=canonical),
            pl.Series(name="timezone_offset_minutes", values=offset),
        ]))


step = TimezoneResolveStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

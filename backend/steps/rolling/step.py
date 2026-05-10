"""Rolling window step.

Adds rolling-window aggregations alongside the existing columns. Polars has
two flavors: row-window (an integer N) and time-window (e.g. '7d') — we
support both via the same `window` field; if it parses as int we use row
windows, else we treat it as a duration string and use the time variant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsResult, Step


def _is_duration_str(s: str) -> bool:
    return any(s.endswith(suf) for suf in ("ns", "us", "ms", "s", "m", "h", "d", "w", "mo", "y", "i"))


class RollingStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx=None,
    ) -> PolarsResult:
        df = inputs["in"]
        tcol = (params.get("time_column") or "").strip() or None
        windows = params.get("windows") or []
        min_periods = int(params.get("min_periods") or 1)

        if not windows:
            raise ValueError("rolling: 'windows' must not be empty")

        if tcol:
            if tcol not in df.columns:
                raise ValueError(f"rolling: time column '{tcol}' not found")
            if df.schema[tcol] == pl.Utf8:
                df = df.with_columns(pl.col(tcol).str.to_datetime(strict=False))
            df = df.sort(tcol)

        out = df.clone()
        for w in windows:
            col = (w.get("column") or "").strip()
            fn = (w.get("fn") or "mean").lower()
            window = w.get("window")
            alias = (w.get("as") or f"{col}_rolling_{fn}_{window}").strip()
            if col not in out.columns:
                raise ValueError(f"rolling: column '{col}' not found")

            time_window = isinstance(window, str) and _is_duration_str(window)
            if time_window:
                if not tcol:
                    raise ValueError(f"rolling: time-based window '{window}' requires time_column")
                expr = pl.col(col).rolling_mean_by(by=tcol, window_size=window, min_samples=min_periods) \
                    if fn == "mean" else None
                if fn == "sum":
                    expr = pl.col(col).rolling_sum_by(by=tcol, window_size=window, min_samples=min_periods)
                elif fn == "min":
                    expr = pl.col(col).rolling_min_by(by=tcol, window_size=window, min_samples=min_periods)
                elif fn == "max":
                    expr = pl.col(col).rolling_max_by(by=tcol, window_size=window, min_samples=min_periods)
                elif fn == "std":
                    expr = pl.col(col).rolling_std_by(by=tcol, window_size=window, min_samples=min_periods)
                if expr is None and fn not in ("mean",):
                    raise ValueError(f"rolling: fn '{fn}' not supported for time windows (use row-count)")
            else:
                n = int(window)
                expr = {
                    "mean":  pl.col(col).rolling_mean(window_size=n, min_samples=min_periods),
                    "sum":   pl.col(col).rolling_sum(window_size=n, min_samples=min_periods),
                    "min":   pl.col(col).rolling_min(window_size=n, min_samples=min_periods),
                    "max":   pl.col(col).rolling_max(window_size=n, min_samples=min_periods),
                    "std":   pl.col(col).rolling_std(window_size=n, min_samples=min_periods),
                    "count": pl.col(col).rolling_map(lambda s: s.len(), window_size=n, min_samples=min_periods),
                }.get(fn)
                if expr is None:
                    raise ValueError(f"rolling: unsupported fn '{fn}'")

            out = out.with_columns(expr.alias(alias))

        return PolarsResult(output=out)


step = RollingStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""Seasonal decomposition step (statsmodels).

Splits a time series into trend, seasonal, and residual components and adds
three columns to the output. Renders a 4-panel plot (observed / trend /
seasonal / residual) as a side-effect artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.engine.chart_defaults import DEFAULT_DPI, TALL_STACK_FIGSIZE


def _detect_period(times) -> int:
    """Best-effort guess at the seasonal period from a sorted time series."""
    import numpy as np
    if len(times) < 4:
        return 0
    deltas = np.diff(times.astype("datetime64[s]").astype("int64"))
    if len(deltas) == 0:
        return 0
    median_dt = float(np.median(deltas))
    seconds_per_day = 86_400
    # Heuristic: hourly → 24, daily → 7, weekly → 52, monthly → 12.
    if median_dt < seconds_per_day * 0.6:
        return 24
    if median_dt < seconds_per_day * 1.5:
        return 7
    if median_dt < seconds_per_day * 10:
        return 52
    return 12


class SeasonalDecomposeStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from statsmodels.tsa.seasonal import seasonal_decompose

        df = inputs["in"]
        tcol = (params.get("time_column") or "").strip()
        vcol = (params.get("value_column") or "").strip()
        model = (params.get("model") or "additive").lower()
        period = int(params.get("period") or 0)

        if tcol not in df.columns or vcol not in df.columns:
            raise ValueError("seasonal_decompose: time and value columns must exist")

        if df.schema[tcol] == pl.Utf8:
            df = df.with_columns(pl.col(tcol).str.to_datetime(strict=False))
        df = df.sort(tcol)

        ts = df.get_column(vcol).to_numpy()
        times = df.get_column(tcol).to_numpy()

        if period <= 0:
            period = _detect_period(times)
        if period < 2:
            raise ValueError("seasonal_decompose: could not infer a period >= 2; set 'period' explicitly")
        if df.height < period * 2:
            raise ValueError(
                f"seasonal_decompose: need at least 2 periods of data ({period * 2}); have {df.height}"
            )

        result = seasonal_decompose(ts, model=model, period=period, extrapolate_trend="freq")

        out = df.with_columns([
            pl.Series("trend",     result.trend),
            pl.Series("seasonal",  result.seasonal),
            pl.Series("residual",  result.resid),
        ])

        artifacts: list[dict[str, Any]] = []
        artifacts.append({
            "kind": "stats",
            "label": "Seasonal decomposition summary",
            "data": {
                "period": period,
                "model": model,
                "n_obs": df.height,
                "trend_strength": _strength(result.trend, result.resid),
                "seasonal_strength": _strength(result.seasonal, result.resid),
            },
        })

        if bool(params.get("render", True)) and ctx is not None:
            artifacts.append(self._render(out, tcol, vcol, params, ctx))

        return PolarsResult(output=out, artifacts=artifacts)

    def _render(
        self,
        df: pl.DataFrame,
        tcol: str,
        vcol: str,
        params: dict[str, Any],
        ctx: PolarsContext,
    ) -> dict[str, Any]:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="whitegrid", context="notebook")

        title = params.get("title") or "Seasonal decomposition"
        x = df.get_column(tcol).to_numpy()
        rows = [
            (vcol,        df.get_column(vcol).to_numpy()),
            ("trend",     df.get_column("trend").to_numpy()),
            ("seasonal",  df.get_column("seasonal").to_numpy()),
            ("residual",  df.get_column("residual").to_numpy()),
        ]
        fig, axes = plt.subplots(4, 1, figsize=TALL_STACK_FIGSIZE, dpi=DEFAULT_DPI, sharex=True)
        for ax, (label, ys) in zip(axes, rows):
            ax.plot(x, ys, linewidth=1.2)
            ax.set_ylabel(label)
        axes[0].set_title(title)
        axes[-1].set_xlabel(tcol)
        fig.tight_layout()

        out_path = ctx.out_dir / f"{self.id}.png"
        fig.savefig(out_path, format="png", dpi=DEFAULT_DPI, bbox_inches="tight")
        plt.close(fig)

        return {
            "kind": "image",
            "format": "png",
            "path": str(out_path),
            "chart": "seasonal_decompose",
            "title": title,
            "rows_plotted": df.height,
        }


def _strength(component, residual) -> float:
    """Hyndman strength-of-component metric: 1 - var(residual) / var(component+residual)."""
    import numpy as np
    a = np.asarray(component, dtype=float)
    r = np.asarray(residual, dtype=float)
    a = a[np.isfinite(a)]; r = r[np.isfinite(r)]
    n = min(len(a), len(r))
    if n == 0:
        return 0.0
    a, r = a[-n:], r[-n:]
    var_r = float(np.var(r))
    var_total = float(np.var(a + r))
    if var_total == 0:
        return 0.0
    return float(max(0.0, 1.0 - var_r / var_total))


step = SeasonalDecomposeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

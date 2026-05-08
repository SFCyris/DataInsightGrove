"""Forecast step.

Holt-Winters / ETS forecast via statsmodels. Extends the input with N future
rows containing a 'forecast' column and 'forecast_lo' / 'forecast_hi' 95%
prediction intervals. Renders a plot showing fit + forecast with shaded
interval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.engine.chart_defaults import DEFAULT_DPI, WIDE_FIGSIZE


def _detect_period(times) -> int:
    import numpy as np
    if len(times) < 4:
        return 0
    deltas = np.diff(times.astype("datetime64[s]").astype("int64"))
    if len(deltas) == 0:
        return 0
    median_dt = float(np.median(deltas))
    spd = 86_400
    if median_dt < spd * 0.6:
        return 24
    if median_dt < spd * 1.5:
        return 7
    if median_dt < spd * 10:
        return 52
    return 12


def _infer_freq(times):
    import numpy as np
    if len(times) < 2:
        return "1d"
    deltas = np.diff(times.astype("datetime64[s]").astype("int64"))
    median_dt = int(np.median(deltas))
    spd = 86_400
    if median_dt <= 60:
        return f"{median_dt}s"
    if median_dt <= 3600:
        return f"{median_dt // 60}m"
    if median_dt < spd:
        return f"{median_dt // 3600}h"
    return f"{max(1, round(median_dt / spd))}d"


class ForecastStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        tcol = (params.get("time_column") or "").strip()
        vcol = (params.get("value_column") or "").strip()
        horizon = int(params.get("horizon") or 30)
        method = (params.get("method") or "auto").lower()
        period = int(params.get("seasonal_period") or 0)

        if tcol not in df.columns or vcol not in df.columns:
            raise ValueError("forecast: time and value columns must exist")

        if df.schema[tcol] == pl.Utf8:
            df = df.with_columns(pl.col(tcol).str.to_datetime(strict=False))
        df = df.sort(tcol).drop_nulls(subset=[tcol, vcol])

        ts = df.get_column(vcol).to_numpy(allow_copy=True)
        times = df.get_column(tcol).to_numpy()
        n = len(ts)
        if n < 6:
            raise ValueError(f"forecast: need at least 6 observations; have {n}")

        if period <= 0:
            period = _detect_period(times)

        if method == "auto":
            method = "holt_winters" if (period >= 2 and n >= period * 2) else "ets"

        forecast, lo, hi = self._fit_and_predict(method, ts, period, n, horizon)

        # Build the future timestamps. Step size = the median gap of the
        # observed series; fall back to 1 day if the series is too short or
        # has duplicate timestamps (otherwise delta_ns would be 0 and
        # future_ns would collapse onto a single point).
        import numpy as np
        freq_str = _infer_freq(times)
        last = df.get_column(tcol).last()
        ONE_DAY_NS = 86_400 * 1_000_000_000
        if n >= 2:
            delta_ns = int(
                (np.datetime64(times[-1]) - np.datetime64(times[-2]))
                .astype("timedelta64[ns]").astype("int64")
            )
        else:
            delta_ns = ONE_DAY_NS
        if delta_ns <= 0:
            delta_ns = ONE_DAY_NS
        last_ns = np.datetime64(last).astype("datetime64[ns]").astype("int64")
        future_ns = [last_ns + delta_ns * (i + 1) for i in range(horizon)]
        future_dt = np.array(future_ns, dtype="datetime64[ns]")
        future_df = pl.DataFrame({tcol: pl.Series(future_dt)})

        # Carry over other columns as null in the future rows.
        for col in df.columns:
            if col in (tcol,):
                continue
            future_df = future_df.with_columns(pl.lit(None).cast(df.schema[col]).alias(col))

        # Annotate fit + forecast.
        df = df.with_columns([
            pl.lit(False).alias("is_forecast"),
            pl.lit(None, dtype=pl.Float64).alias("forecast"),
            pl.lit(None, dtype=pl.Float64).alias("forecast_lo"),
            pl.lit(None, dtype=pl.Float64).alias("forecast_hi"),
        ])
        future_df = future_df.with_columns([
            pl.lit(True).alias("is_forecast"),
            pl.Series("forecast", forecast),
            pl.Series("forecast_lo", lo),
            pl.Series("forecast_hi", hi),
        ])
        # Make column orders match before vstack.
        future_df = future_df.select(df.columns)
        out = pl.concat([df, future_df], how="vertical_relaxed").sort(tcol)

        artifacts: list[dict[str, Any]] = []
        artifacts.append({
            "kind": "stats",
            "label": "Forecast summary",
            "data": {
                "method": method,
                "horizon": horizon,
                "seasonal_period": period,
                "n_train_obs": n,
                "freq": freq_str,
            },
        })
        if bool(params.get("render", True)) and ctx is not None:
            artifacts.append(self._render(out, tcol, vcol, params, ctx))

        return PolarsResult(output=out, artifacts=artifacts)

    def _fit_and_predict(self, method: str, ts, period: int, n: int, horizon: int):
        import numpy as np
        if method == "naive":
            last_value = float(ts[-1])
            forecast = np.full(horizon, last_value)
            sigma = float(np.std(np.diff(ts))) if n >= 2 else 0.0
            half = 1.96 * sigma * np.sqrt(np.arange(1, horizon + 1))
            return forecast, forecast - half, forecast + half

        if method == "holt_winters" and period >= 2 and n >= period * 2:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            model = ExponentialSmoothing(
                ts,
                trend="add",
                seasonal="add",
                seasonal_periods=period,
                initialization_method="estimated",
            ).fit(optimized=True)
            forecast = np.asarray(model.forecast(horizon), dtype=float)
            # Crude PI from in-sample residual std × √h.
            resid = ts - model.fittedvalues
            sigma = float(np.std(resid))
            half = 1.96 * sigma * np.sqrt(np.arange(1, horizon + 1))
            return forecast, forecast - half, forecast + half

        # ETS / non-seasonal Holt fall-through.
        from statsmodels.tsa.exponential_smoothing.ets import ETSModel
        try:
            model = ETSModel(ts, error="add", trend="add", seasonal=None,
                             initialization_method="estimated").fit(disp=False)
            forecast = np.asarray(model.forecast(horizon), dtype=float)
            resid = ts - model.fittedvalues
            sigma = float(np.std(resid))
            half = 1.96 * sigma * np.sqrt(np.arange(1, horizon + 1))
            return forecast, forecast - half, forecast + half
        except Exception:
            # Last resort: naive
            return self._fit_and_predict("naive", ts, period, n, horizon)

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

        title = params.get("title") or "Forecast"

        history = df.filter(~pl.col("is_forecast"))
        future = df.filter(pl.col("is_forecast"))

        fig, ax = plt.subplots(figsize=WIDE_FIGSIZE, dpi=DEFAULT_DPI)
        ax.plot(
            history.get_column(tcol).to_numpy(),
            history.get_column(vcol).to_numpy(),
            color="steelblue", linewidth=1.4, label="observed",
        )
        if future.height > 0:
            xs = future.get_column(tcol).to_numpy()
            ys = future.get_column("forecast").to_numpy()
            lo = future.get_column("forecast_lo").to_numpy()
            hi = future.get_column("forecast_hi").to_numpy()
            ax.plot(xs, ys, color="crimson", linewidth=1.6, label="forecast")
            ax.fill_between(xs, lo, hi, color="crimson", alpha=0.18, label="95% PI")
        ax.set_title(title)
        ax.set_xlabel(tcol); ax.set_ylabel(vcol)
        ax.legend(fontsize=9)
        fig.autofmt_xdate()
        fig.tight_layout()

        # Use node_id, not step-class id — multiple `forecast` nodes in the
        # same pipeline would otherwise overwrite each other's PNG.
        slug = ctx.node_id or self.id
        out_path = ctx.out_dir / f"{slug}.png"
        fig.savefig(out_path, format="png", dpi=DEFAULT_DPI, bbox_inches="tight")
        plt.close(fig)

        return {
            "kind": "image",
            "format": "png",
            "path": str(out_path),
            "chart": "forecast",
            "title": title,
            "rows_plotted": df.height,
        }


step = ForecastStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

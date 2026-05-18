"""candlestick_chart — financial OHLC chart with optional volume sub-panel."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _resolve_out(ctx, custom, step_id):
    if custom:
        p = Path(custom)
        if ctx is not None and not p.is_absolute():
            return ctx.out_dir / p
        return p
    base = ctx.out_dir if ctx is not None else Path.cwd()
    return base / f"{step_id}.png"


class CandlestickChartStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import numpy as np

        df = inputs["in"]
        d_col = params["dateColumn"]; o_col = params["openColumn"]; h_col = params["highColumn"]
        l_col = params["lowColumn"]; c_col = params["closeColumn"]
        v_col = params.get("volumeColumn")
        title = params.get("title", "Candlestick chart")

        clean = df.drop_nulls(subset=[d_col, o_col, h_col, l_col, c_col]).sort(d_col)
        dates = clean[d_col].to_list()
        opens = clean[o_col].to_list()
        highs = clean[h_col].to_list()
        lows = clean[l_col].to_list()
        closes = clean[c_col].to_list()
        volumes = clean[v_col].to_list() if v_col and v_col in clean.columns else None

        if not dates:
            raise ValueError("candlestick_chart: no rows after drop_nulls")

        # Figure layout: candles on top, volume bar (if present) on bottom.
        if volumes is not None:
            fig, (ax, ax_vol) = plt.subplots(2, 1, figsize=(12, 7), dpi=144,
                                                gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
        else:
            fig, ax = plt.subplots(figsize=(12, 6), dpi=144)
            ax_vol = None

        # Compute bar width as a fraction of the median date spacing.
        x_nums = mdates.date2num(dates)
        if len(x_nums) >= 2:
            spacings = np.diff(x_nums)
            width = float(np.median(spacings)) * 0.6 if len(spacings) > 0 else 0.6
        else:
            width = 0.6

        for i, x in enumerate(x_nums):
            o = float(opens[i]); h = float(highs[i]); lo = float(lows[i]); c = float(closes[i])
            up = c >= o
            color = "#10b981" if up else "#ef4444"
            ax.plot([x, x], [lo, h], color="#374151", linewidth=0.8)
            body_low = min(o, c); body_high = max(o, c)
            ax.add_patch(plt.Rectangle((x - width / 2, body_low), width, max(body_high - body_low, 1e-6),
                                          facecolor=color, edgecolor="#374151", linewidth=0.5))
        ax.set_title(title); ax.set_ylabel("price")
        ax.xaxis_date(); ax.grid(True, alpha=0.2)
        ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(mdates.AutoDateLocator()))

        if ax_vol is not None and volumes is not None:
            for i, x in enumerate(x_nums):
                up = float(closes[i]) >= float(opens[i])
                ax_vol.bar(x, float(volumes[i]) if volumes[i] is not None else 0,
                            width=width, color="#10b981" if up else "#ef4444", alpha=0.6)
            ax_vol.set_ylabel("volume")
            ax_vol.grid(True, alpha=0.2)
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out_path),
            "chart": "candlestick", "title": title, "n_bars": len(dates),
        }])


step = CandlestickChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

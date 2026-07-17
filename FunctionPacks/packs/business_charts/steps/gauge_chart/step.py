"""gauge_chart — speedometer-style single-metric chart."""
from __future__ import annotations

import json
import math
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


class GaugeChartStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np

        df = inputs["in"]
        l_col = params["labelColumn"]; v_col = params["valueColumn"]
        v_min = float(params.get("minValue", 0.0))
        v_max = float(params.get("maxValue", 100.0))
        red_max = params.get("redMax")
        amber_max = params.get("amberMax")
        if red_max is None:
            red_max = v_min + 0.30 * (v_max - v_min)
        if amber_max is None:
            amber_max = v_min + 0.70 * (v_max - v_min)
        title = params.get("title", "Gauge")

        clean = df.drop_nulls(subset=[l_col, v_col])
        labels = [str(v) for v in clean[l_col].to_list()]
        values = [float(v) for v in clean[v_col].to_list()]
        n = len(labels)
        if n == 0:
            raise ValueError("gauge_chart: no rows after drop_nulls")

        cols = min(n, 3)
        rows = math.ceil(n / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.2 * rows), dpi=144, squeeze=False)
        for idx in range(rows * cols):
            ax = axes[idx // cols][idx % cols]
            if idx >= n:
                ax.axis("off")
                continue
            label = labels[idx]; value = values[idx]
            # Draw the three-color arc.
            for vmin, vmax, color in [(v_min, red_max, "#ef4444"),
                                        (red_max, amber_max, "#f59e0b"),
                                        (amber_max, v_max, "#10b981")]:
                start = 180 * (1 - (vmax - v_min) / max(1e-9, v_max - v_min))
                end = 180 * (1 - (vmin - v_min) / max(1e-9, v_max - v_min))
                arc = mpatches.Wedge(center=(0, 0), r=1.0, theta1=start, theta2=end,
                                       width=0.25, facecolor=color, edgecolor="white")
                ax.add_patch(arc)
            # Needle.
            t_clamped = max(v_min, min(v_max, value))
            theta = math.pi * (1 - (t_clamped - v_min) / max(1e-9, v_max - v_min))
            ax.plot([0, 0.85 * math.cos(theta)], [0, 0.85 * math.sin(theta)],
                     color="#111827", linewidth=3)
            ax.add_patch(mpatches.Circle((0, 0), 0.05, facecolor="#111827", edgecolor="white", zorder=5))
            ax.text(0, -0.25, f"{value:,.1f}", ha="center", va="center", fontsize=18, fontweight="bold")
            ax.text(0, -0.45, label, ha="center", va="center", fontsize=11, color="#6b7280")
            ax.set_xlim(-1.2, 1.2); ax.set_ylim(-0.6, 1.2); ax.set_aspect("equal")
            ax.axis("off")
        if title:
            fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out_path),
            "chart": "gauge", "title": title, "n_gauges": n,
        }])


step = GaugeChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

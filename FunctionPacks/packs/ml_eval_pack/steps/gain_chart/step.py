"""gain_chart — cumulative gains curve."""
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


class GainChartStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        df = inputs["in"]
        actual = params["actualColumn"]; proba = params["probaColumn"]
        title = params.get("title", "Cumulative gains")

        clean = df.drop_nulls(subset=[actual, proba])
        y = np.asarray([int(bool(v)) for v in clean[actual].to_list()])
        s = np.asarray([float(v) for v in clean[proba].to_list()])
        if y.sum() == 0 or len(y) == 0:
            raise ValueError("gain_chart: actual must contain at least one positive class")

        order = np.argsort(-s)
        y_sorted = y[order]
        cum_pos = np.cumsum(y_sorted) / y.sum()
        cum_pop = np.arange(1, len(y) + 1) / len(y)

        fig, ax = plt.subplots(figsize=(8, 6), dpi=144)
        ax.plot(cum_pop, cum_pos, color="#10b981", linewidth=2, label="Model")
        ax.plot([0, 1], [0, 1], color="#9ca3af", linestyle="--", linewidth=1, label="Random")
        # Optimal: positives reached as fast as the base rate allows.
        base_rate = y.sum() / len(y)
        optimal_x = np.linspace(0, base_rate, 50)
        optimal_y = optimal_x / base_rate
        ax.plot(np.concatenate([optimal_x, [1.0]]), np.concatenate([optimal_y, [1.0]]),
                 color="#06b6d4", linestyle=":", linewidth=1, label="Optimal")
        ax.fill_between(cum_pop, cum_pos, cum_pop, alpha=0.1, color="#10b981")
        ax.set_xlim([0, 1]); ax.set_ylim([0, 1.02])
        ax.set_xlabel("Fraction of population (sorted by probability)")
        ax.set_ylabel("Fraction of positives captured")
        ax.set_title(title); ax.legend(loc="lower right"); ax.grid(True, alpha=0.3)

        out = _resolve_out(ctx, params.get("output_path"), self.id)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out),
            "chart": "gain_chart", "title": title, "n_samples": len(y),
        }])


step = GainChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

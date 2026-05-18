"""stream_graph — center-baselined stacked area chart."""
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


class StreamGraphStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import numpy as np

        df = inputs["in"]
        d_col = params["dateColumn"]
        g_col = params["groupColumn"]
        v_col = params["valueColumn"]
        scale = params.get("color_scale", "viridis")
        title = params.get("title", "Stream graph")

        clean = df.drop_nulls(subset=[d_col, g_col, v_col]).sort(d_col)
        if clean.height == 0:
            raise ValueError("stream_graph: no rows after drop_nulls")
        # Pivot: rows = date, cols = group, value = sum
        pivot = (clean.group_by([d_col, g_col]).agg(pl.col(v_col).sum().alias("__v"))
                       .pivot(values="__v", index=d_col, on=g_col, aggregate_function="sum")
                       .fill_null(0).sort(d_col))
        x = pivot[d_col].to_list()
        groups = [c for c in pivot.columns if c != d_col]
        if not groups:
            raise ValueError("stream_graph: no groups after pivot")
        Y = np.asarray(pivot.drop(d_col).to_numpy(), dtype=float)  # (T, G)
        # Center baseline: shift the stacked totals so the symmetry axis is zero.
        # Lower edges = -row_total/2; upper edges accumulate from there.
        row_totals = Y.sum(axis=1)
        # Avoid division by zero at all-zero columns.
        baseline = -row_totals / 2

        cmap = plt.colormaps.get_cmap(scale)
        colors = [cmap(i / max(1, len(groups) - 1)) for i in range(len(groups))]

        fig, ax = plt.subplots(figsize=(12, 6), dpi=144)
        cursor = baseline.copy()
        for i, g in enumerate(groups):
            top = cursor + Y[:, i]
            ax.fill_between(x, cursor, top, color=colors[i], alpha=0.85, label=str(g))
            cursor = top
        ax.set_title(title)
        ax.set_xlabel(d_col); ax.set_ylabel(v_col)
        ax.legend(bbox_to_anchor=(1.02, 1.0), loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.2)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out_path),
            "chart": "streamgraph", "title": title, "n_series": len(groups), "n_periods": len(x),
        }])


step = StreamGraphStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

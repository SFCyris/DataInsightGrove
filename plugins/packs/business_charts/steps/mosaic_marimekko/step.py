"""mosaic_marimekko — 2-D part-to-whole rectangle chart."""
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


class MosaicMarimekkoStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import numpy as np

        df = inputs["in"]
        row_g = params["rowGroup"]; col_g = params["columnGroup"]; val = params["valueColumn"]
        title = params.get("title", "Marimekko")

        clean = df.drop_nulls(subset=[row_g, col_g, val]).filter(pl.col(val) > 0)
        if clean.height == 0:
            raise ValueError("mosaic_marimekko: no rows with positive value")
        # Pivot: rows = row_g, cols = col_g, cells = sum(value)
        pivot = clean.pivot(values=val, index=row_g, on=col_g, aggregate_function="sum").fill_null(0)
        row_labels = [str(v) for v in pivot[row_g].cast(pl.Utf8).to_list()]
        col_labels = [c for c in pivot.columns if c != row_g]
        mat = np.asarray(pivot.drop(row_g).to_numpy(), dtype=float)
        if mat.size == 0:
            raise ValueError("mosaic_marimekko: empty pivot")

        # Sort rows by total descending so wider columns come first.
        row_totals = mat.sum(axis=1)
        order = np.argsort(-row_totals)
        mat = mat[order]
        row_labels = [row_labels[i] for i in order]
        row_totals = row_totals[order]
        grand_total = row_totals.sum()
        if grand_total == 0:
            raise ValueError("mosaic_marimekko: grand total is zero")

        # Column widths proportional to row totals.
        widths = row_totals / grand_total

        cmap = cm.tab10 if len(col_labels) <= 10 else cm.tab20
        colors = [cmap(i / max(1, len(col_labels) - 1)) for i in range(len(col_labels))]

        fig, ax = plt.subplots(figsize=(12, 7), dpi=144)
        x_cursor = 0.0
        for r_idx, row_w in enumerate(widths):
            row_sum = row_totals[r_idx]
            heights = mat[r_idx] / row_sum
            y_cursor = 0.0
            for c_idx, h in enumerate(heights):
                ax.add_patch(plt.Rectangle((x_cursor, y_cursor), row_w, h,
                                              facecolor=colors[c_idx], edgecolor="white", linewidth=1.5))
                if h > 0.04 and row_w > 0.03:
                    ax.text(x_cursor + row_w / 2, y_cursor + h / 2, f"{h * 100:.0f}%",
                             ha="center", va="center", color="white", fontsize=9, fontweight="bold")
                y_cursor += h
            ax.text(x_cursor + row_w / 2, -0.04, row_labels[r_idx], ha="center", va="top", fontsize=10)
            x_cursor += row_w

        ax.set_xlim(0, 1); ax.set_ylim(-0.08, 1)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels([f"{int(p * 100)}%" for p in [0, 0.25, 0.5, 0.75, 1.0]])
        ax.set_xticks([])
        ax.set_title(title)
        # Legend.
        import matplotlib.patches as mpatches
        handles = [mpatches.Patch(color=colors[i], label=col_labels[i]) for i in range(len(col_labels))]
        ax.legend(handles=handles, title=col_g, bbox_to_anchor=(1.02, 1.0), loc="upper left")

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out_path),
            "chart": "marimekko", "title": title, "n_rows": len(row_labels), "n_cols": len(col_labels),
        }])


step = MosaicMarimekkoStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""ridge_plot — Joy-Division-style stacked density plot."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _resolve_out(ctx: PolarsContext | None, custom: str | None, step_id: str) -> Path:
    if custom:
        p = Path(custom)
        if ctx is not None and not p.is_absolute():
            return ctx.out_dir / p
        return p
    base = ctx.out_dir if ctx is not None else Path.cwd()
    return base / f"{step_id}.png"


class RidgePlotStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import numpy as np
        from scipy.stats import gaussian_kde

        df = inputs["in"]
        value = params["value"]
        group = params["group"]
        scale = params.get("color_scale", "viridis")
        overlap = float(params.get("overlap", 0.5))
        title = params.get("title", "Ridge plot")

        clean = df.select([value, group]).drop_nulls()
        if clean.height == 0:
            raise ValueError("ridge_plot: no rows after drop_nulls")
        groups = clean[group].unique().sort().to_list()
        n = len(groups)
        if n == 0:
            raise ValueError("ridge_plot: no groups found")

        # Common x grid spanning the data range.
        all_x = clean[value].to_numpy()
        x_min, x_max = float(np.nanmin(all_x)), float(np.nanmax(all_x))
        x_grid = np.linspace(x_min, x_max, 400)

        cmap = plt.colormaps.get_cmap(scale)
        height_per_row = 0.8
        spacing = height_per_row * (1.0 - overlap)

        fig, ax = plt.subplots(figsize=(10, max(4, 1.2 * n)), dpi=144)
        # Iterate from top (last group) to bottom (first group) so axis
        # labels read top-down naturally.
        for i, g in enumerate(reversed(groups)):
            xs = clean.filter(pl.col(group) == g)[value].to_numpy()
            if len(xs) < 2:
                continue
            try:
                kde = gaussian_kde(xs)
                density = kde(x_grid)
            except Exception:
                continue
            # Normalise density to height_per_row.
            if density.max() > 0:
                density = density / density.max() * height_per_row
            offset = i * spacing
            color = cmap(i / max(1, n - 1))
            ax.fill_between(x_grid, offset, offset + density, color=color, alpha=0.7, edgecolor="white", linewidth=1)
            ax.text(x_min, offset + 0.05, str(g), va="bottom", ha="left", fontsize=10,
                     color="black", bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.7))
        ax.set_yticks([])
        ax.set_xlabel(value)
        ax.set_title(title)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "image", "format": "png", "path": str(out_path),
                "chart": "ridge", "title": title, "n_groups": n,
            }],
        )


step = RidgePlotStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

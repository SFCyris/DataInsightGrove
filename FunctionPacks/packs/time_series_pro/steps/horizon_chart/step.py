"""horizon_chart — banded small-multiples for many time series."""
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


class HorizonChartStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        df = inputs["in"]
        d_col = params["dateColumn"]; g_col = params["groupColumn"]; v_col = params["valueColumn"]
        n_bands = int(params.get("bands", 3))
        title = params.get("title", "Horizon chart")

        clean = df.drop_nulls(subset=[d_col, g_col, v_col]).sort(d_col)
        groups = clean[g_col].unique().sort().to_list()
        n = len(groups)
        if n == 0:
            raise ValueError("horizon_chart: no groups found")

        # Compute thresholds globally so cross-series comparison is honest.
        all_vals = np.asarray(clean[v_col].to_numpy(), dtype=float)
        median = float(np.median(all_vals))
        max_dev = float(np.max(np.abs(all_vals - median)) or 1.0)
        band_step = max_dev / n_bands

        pos_cmap = plt.colormaps.get_cmap("Blues")
        neg_cmap = plt.colormaps.get_cmap("Reds")

        fig, axes = plt.subplots(n, 1, figsize=(11, max(0.55 * n, 3)), dpi=144,
                                    sharex=True, gridspec_kw={"hspace": 0.0}, squeeze=False)
        axes = axes[:, 0]
        for i, g in enumerate(groups):
            ax = axes[i]
            sub = clean.filter(pl.col(g_col) == g).sort(d_col)
            x = sub[d_col].to_list()
            y = np.asarray(sub[v_col].to_numpy(), dtype=float) - median
            # Plot one band at a time, stacking darker shades closer to extremes.
            for b in range(n_bands):
                lo = b * band_step; hi = (b + 1) * band_step
                # Positive band b: contribution is min(max(y - lo, 0), band_step).
                pos_contrib = np.clip(y - lo, 0, band_step)
                if pos_contrib.max() > 0:
                    ax.fill_between(x, 0, pos_contrib, color=pos_cmap(0.4 + 0.6 * b / n_bands), linewidth=0)
                neg_contrib = np.clip(-y - lo, 0, band_step)
                if neg_contrib.max() > 0:
                    ax.fill_between(x, 0, neg_contrib, color=neg_cmap(0.4 + 0.6 * b / n_bands), linewidth=0)
            ax.set_ylim(0, band_step * 1.05)
            ax.set_yticks([])
            ax.text(-0.005, 0.5, str(g), transform=ax.transAxes, ha="right", va="center", fontsize=9)
            for spine in ("top", "right", "left", "bottom"):
                ax.spines[spine].set_visible(False)
        axes[-1].tick_params(axis="x", labelsize=8)
        fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out_path),
            "chart": "horizon", "title": title, "n_series": n,
        }])


step = HorizonChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

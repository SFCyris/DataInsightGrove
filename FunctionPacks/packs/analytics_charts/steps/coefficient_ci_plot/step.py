"""coefficient_ci_plot — forest plot of coefficient point estimates + CI."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class CoefficientCiPlotStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        df = inputs["in"]
        f = params["featureColumn"]; e = params["estimateColumn"]
        lo = params["lowerColumn"]; hi = params["upperColumn"]
        title = params.get("title") or "Coefficients with 95% CI"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1000); height = int(params.get("height") or 800)

        clean = df.drop_nulls(subset=[f, e, lo, hi]).sort(e)
        feats = [str(v) for v in clean[f].to_list()]
        est = np.asarray([float(v) for v in clean[e].to_list()])
        lows = np.asarray([float(v) for v in clean[lo].to_list()])
        ups = np.asarray([float(v) for v in clean[hi].to_list()])
        err_low = est - lows; err_up = ups - est

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        ys = np.arange(len(feats))
        # Color: significantly above zero = green, significantly below = red, spans zero = grey.
        colors = ["#10b981" if low > 0 else "#ef4444" if up < 0 else "#9ca3af"
                  for low, up in zip(lows, ups)]
        ax.errorbar(est, ys, xerr=[err_low, err_up], fmt="o", capsize=3,
                     ecolor="#374151", markerfacecolor="white", markeredgecolor="#374151")
        # Color the markers per significance.
        ax.scatter(est, ys, c=colors, s=80, zorder=3, edgecolor="#374151")
        ax.axvline(0, color="#9ca3af", linestyle="--", linewidth=1)
        ax.set_yticks(ys); ax.set_yticklabels(feats)
        ax.set_xlabel("Coefficient (95% CI)"); ax.set_title(title)
        ax.grid(True, alpha=0.2, axis="x")

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "coefficient_ci_plot",
            "title": title, "n_features": len(feats),
        }])


step = CoefficientCiPlotStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

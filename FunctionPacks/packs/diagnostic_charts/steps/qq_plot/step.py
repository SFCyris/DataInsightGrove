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


class QqPlotStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from scipy import stats
        import numpy as np

        df = inputs["in"]
        value = params["value"]
        title = params.get("title", "Q-Q plot vs. normal")

        x = df[value].drop_nulls().to_numpy()
        if len(x) < 5:
            raise ValueError(f"qq_plot: need ≥5 non-null observations, got {len(x)}")

        fig, ax = plt.subplots(figsize=(6, 6), dpi=144)
        # statsmodels.api.qqplot would be nicer but adds a dep — use scipy instead.
        osm, osr = stats.probplot(x, dist="norm", fit=False)
        ax.scatter(osm, osr, alpha=0.6, s=10)
        # 45° reference line through (0, mean) with slope = std
        x_line = np.linspace(osm.min(), osm.max(), 50)
        slope = np.std(x, ddof=1)
        intercept = np.mean(x)
        ax.plot(x_line, slope * x_line + intercept, "r--", linewidth=1)
        ax.set_xlabel("Theoretical quantiles")
        ax.set_ylabel("Sample quantiles")
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "image", "format": "png", "path": str(out_path),
                "chart": "qq", "title": title, "rows_plotted": int(len(x)),
            }],
        )


step = QqPlotStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

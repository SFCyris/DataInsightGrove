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


class FunnelChartStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        df = inputs["in"]
        stage_col = params["stage"]
        value_col = params["value"]
        title = params.get("title", "Funnel")

        clean = df.select([stage_col, value_col]).drop_nulls()
        if clean.height == 0:
            raise ValueError("funnel_chart: no non-null rows")
        stages = clean[stage_col].cast(pl.Utf8).to_list()
        values = clean[value_col].to_numpy().astype(float)

        max_v = float(values.max())
        # Normalised widths so the funnel narrows visually.
        widths = values / max_v
        fig, ax = plt.subplots(figsize=(10, max(4, 0.6 * len(stages))), dpi=144)
        # Layout: stage labels on the LEFT (dark, always visible),
        # bar centered with the count INSIDE in white, conversion %
        # on the RIGHT in dark. This keeps every label readable
        # regardless of how narrow the bar gets — the previous design
        # rendered everything inside the bar in white, which became
        # white-on-white once the bar narrowed past the text width.
        for i, (s, v, w) in enumerate(zip(stages, values, widths)):
            left = (1.0 - w) / 2.0
            ax.barh(i, w, left=left, height=0.7, color="#1f77b4", edgecolor="white")
            # Stage name on the far left, dark.
            ax.text(
                -0.01, i, s, ha="right", va="center",
                color="#222", fontsize=10, fontweight="bold",
            )
            # Count inside the bar — white, only positioned where the
            # bar actually exists. When the bar is too narrow even for
            # the count, fall back to dark text just outside the right
            # edge so it never collides with white background.
            count_text = f"{v:,.0f}"
            est_text_width = max(0.05, len(count_text) * 0.013)
            if w >= est_text_width:
                ax.text(
                    0.5, i, count_text, ha="center", va="center",
                    color="white", fontsize=10, fontweight="bold",
                )
            else:
                ax.text(
                    left + w + 0.005, i, count_text, ha="left", va="center",
                    color="#222", fontsize=10, fontweight="bold",
                )
            # Conversion-vs-previous on the far right, dark.
            if i > 0 and values[i - 1] > 0:
                pct = (v / values[i - 1]) * 100
                ax.text(
                    1.01, i, f"{pct:.1f}% of prev",
                    ha="left", va="center", color="#444", fontsize=9,
                )
        ax.invert_yaxis()
        # Wider xlim leaves explicit room for the side labels so they
        # don't get clipped by tight_layout.
        ax.set_xlim(-0.45, 1.25)
        ax.set_xticks([])
        ax.set_yticks([])
        # Hide spines for a cleaner look — the bars themselves carry
        # the visual structure.
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title(title)
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "image", "format": "png", "path": str(out_path),
                "chart": "funnel", "title": title, "rows_plotted": len(stages),
            }],
        )


step = FunnelChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

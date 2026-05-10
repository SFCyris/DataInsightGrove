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


class WaterfallChartStep(Step):
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
        label_col = params["label"]
        value_col = params["value"]
        title = params.get("title", "Waterfall")

        clean = df.select([label_col, value_col]).drop_nulls()
        labels = clean[label_col].cast(pl.Utf8).to_list()
        values = clean[value_col].to_numpy()
        if len(labels) == 0:
            raise ValueError("waterfall_chart: no non-null rows")

        # Cumulative running total, with one extra bar for the final.
        running = np.concatenate([[0], values.cumsum()])[:-1]
        total = float(values.sum())

        fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.7), 5), dpi=144)
        colors = ["#1f77b4" if v >= 0 else "#d62728" for v in values]
        ax.bar(labels, values, bottom=running, color=colors, edgecolor="white")
        # Final total bar
        ax.bar(["Total"], [total], color="#2ca02c", edgecolor="white")
        for i, (lbl, v, run) in enumerate(zip(labels, values, running)):
            ax.text(i, run + v, f"{v:+,.0f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=9)
        ax.text(len(labels), total, f"{total:,.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax.set_title(title)
        ax.axhline(0, color="black", linewidth=0.8)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "image", "format": "png", "path": str(out_path),
                "chart": "waterfall", "title": title, "rows_plotted": len(labels),
            }],
        )


step = WaterfallChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

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


class ParetoChartStep(Step):
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
        top_n = int(params.get("top_n", 20))
        title = params.get("title", "Pareto")

        agg = (
            df.select([label_col, value_col])
              .drop_nulls()
              .group_by(label_col)
              .agg(pl.col(value_col).sum().alias("total"))
              .sort("total", descending=True)
              .head(top_n)
        )
        if agg.height == 0:
            raise ValueError("pareto_chart: no non-null rows")
        labels = agg[label_col].cast(pl.Utf8).to_list()
        values = agg["total"].to_numpy()
        cumulative_pct = (values.cumsum() / values.sum()) * 100

        fig, ax1 = plt.subplots(figsize=(max(8, len(labels) * 0.5), 5), dpi=144)
        ax1.bar(labels, values, color="#1f77b4")
        ax1.set_ylabel(value_col)
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, ha="right")

        ax2 = ax1.twinx()
        ax2.plot(labels, cumulative_pct, color="#ff7f0e", marker="o", linewidth=2)
        ax2.axhline(80, color="grey", linestyle="--", linewidth=0.8)
        ax2.set_ylabel("Cumulative %")
        ax2.set_ylim(0, 105)

        ax1.set_title(title)
        fig.tight_layout()

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "image", "format": "png", "path": str(out_path),
                "chart": "pareto", "title": title, "rows_plotted": len(labels),
            }],
        )


step = ParetoChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

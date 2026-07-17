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


class DensityPlotStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        df = inputs["in"]
        value = params["value"]
        group = params.get("group")
        fill = bool(params.get("fill", True))
        title = params.get("title", "Density")

        fig, ax = plt.subplots(figsize=(8, 5), dpi=144)
        cols = [c for c in (value, group) if c]
        pdf = df.select(cols).drop_nulls().to_pandas()
        if group:
            sns.kdeplot(data=pdf, x=value, hue=group, fill=fill, ax=ax)
        else:
            sns.kdeplot(data=pdf, x=value, fill=fill, ax=ax)
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
                "chart": "density", "title": title, "rows_plotted": pdf.shape[0],
            }],
        )


step = DensityPlotStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

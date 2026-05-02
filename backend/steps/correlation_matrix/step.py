"""Correlation matrix step.

Computes pairwise correlation between numeric columns, returns the result as
a long-form (col_a, col_b, r) DataFrame, and optionally renders a heatmap as
a side-effect image artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _is_numeric(dtype: pl.DataType) -> bool:
    name = str(dtype).lower()
    return any(t in name for t in ("int", "float", "double", "decimal"))


class CorrelationMatrixStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        method = (params.get("method") or "pearson").lower()
        if method not in ("pearson", "spearman", "kendall"):
            raise ValueError(f"correlation_matrix: invalid method '{method}'")

        cols = params.get("columns") or [c for c, t in df.schema.items() if _is_numeric(t)]
        cols = [c for c in cols if c in df.columns]
        if len(cols) < 2:
            raise ValueError("correlation_matrix: need at least 2 numeric columns")

        # Polars has only Pearson via .corr; fall back to pandas/scipy for others.
        pdf = df.select(cols).to_pandas()
        corr = pdf.corr(method=method)

        # Long-form output table: col_a | col_b | r
        rows: list[dict[str, Any]] = []
        for a in cols:
            for b in cols:
                rows.append({"col_a": a, "col_b": b, "r": float(corr.loc[a, b])})
        out_df = pl.DataFrame(rows)

        artifacts: list[dict[str, Any]] = []
        if bool(params.get("render", True)) and ctx is not None:
            artifacts.append(self._render_heatmap(corr, cols, params, ctx))

        return PolarsResult(output=out_df, artifacts=artifacts)

    def _render_heatmap(self, corr, cols: list[str], params: dict[str, Any], ctx: PolarsContext) -> dict[str, Any]:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        title = params.get("title") or "Correlation matrix"
        n = len(cols)
        fig, ax = plt.subplots(figsize=(max(6, n * 0.6), max(5, n * 0.55)), dpi=144)
        sns.heatmap(
            corr.values, ax=ax, cmap="RdBu_r", vmin=-1, vmax=1, center=0,
            annot=n <= 12, fmt=".2f", xticklabels=cols, yticklabels=cols,
            cbar_kws={"label": "r"},
        )
        ax.set_title(title)
        fig.tight_layout()

        out_path = ctx.out_dir / f"{self.id}.png"
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)

        return {
            "kind": "image",
            "format": "png",
            "path": str(out_path),
            "chart": "heatmap",
            "title": title,
            "rows_plotted": n * n,
        }


step = CorrelationMatrixStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

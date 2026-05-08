"""t-SNE step — non-linear 2-D embedding for visualization.

Because t-SNE is O(n²) and inherently sample-dependent, this step:
  - downsamples to `max_rows` if the input is larger
  - emits a frame containing only the sampled rows + tSNE_1, tSNE_2
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.engine.chart_defaults import DEFAULT_DPI, SQUARE_FIGSIZE


def _is_numeric(dtype: pl.DataType) -> bool:
    name = str(dtype).lower()
    return any(t in name for t in ("int", "float", "double", "decimal"))


class TSNEStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.manifold import TSNE
        from sklearn.preprocessing import StandardScaler

        df = inputs["in"]
        cols = params.get("columns") or [c for c, t in df.schema.items() if _is_numeric(t)]
        cols = [c for c in cols if c in df.columns]
        if len(cols) < 2:
            raise ValueError("tsne: need at least 2 numeric columns")

        max_rows = int(params.get("max_rows") or 5000)
        sub = df.drop_nulls(subset=cols)
        if sub.height > max_rows:
            sub = sub.sample(n=max_rows, seed=int(params.get("seed") or 42))

        if sub.height < 10:
            raise ValueError(f"tsne: only {sub.height} complete rows; t-SNE needs many more")

        x = sub.select(cols).to_numpy()
        if bool(params.get("scale", True)):
            x = StandardScaler().fit_transform(x)

        # sklearn's perplexity must be < n_samples; clamp.
        perplexity = float(params.get("perplexity") or 30)
        perplexity = min(perplexity, max(5.0, sub.height / 4.0))

        tsne = TSNE(
            n_components=2,
            perplexity=perplexity,
            random_state=int(params.get("seed") or 42),
            init="pca",
            learning_rate="auto",
        )
        emb = tsne.fit_transform(x)

        out = sub.with_columns([
            pl.Series("tSNE_1", emb[:, 0]),
            pl.Series("tSNE_2", emb[:, 1]),
        ])

        artifacts: list[dict[str, Any]] = []
        artifacts.append({
            "kind": "stats",
            "label": "t-SNE summary",
            "data": {
                "n_rows_embedded": out.height,
                "perplexity_used": perplexity,
                "n_input_features": len(cols),
            },
        })

        if bool(params.get("render", True)) and ctx is not None:
            artifacts.append(self._render(out, params, ctx))

        return PolarsResult(output=out, artifacts=artifacts)

    def _render(self, df: pl.DataFrame, params: dict[str, Any], ctx: PolarsContext) -> dict[str, Any]:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="whitegrid", context="notebook")

        title = params.get("title") or "t-SNE"
        color_by = params.get("color_by")

        fig, ax = plt.subplots(figsize=SQUARE_FIGSIZE, dpi=DEFAULT_DPI)
        xs = df.get_column("tSNE_1").to_numpy()
        ys = df.get_column("tSNE_2").to_numpy()

        if color_by and color_by in df.columns:
            cs = df.get_column(color_by)
            if _is_numeric(cs.dtype):
                sc = ax.scatter(xs, ys, c=cs.to_numpy(), cmap="viridis", alpha=0.7, s=18)
                cb = fig.colorbar(sc, ax=ax)
                cb.set_label(color_by)
            else:
                cats = cs.cast(pl.Utf8).to_list()
                uniq = list(dict.fromkeys(cats))
                palette = sns.color_palette("tab20", n_colors=max(len(uniq), 3))
                for i, c in enumerate(uniq):
                    m = [k == c for k in cats]
                    ax.scatter(
                        [xs[j] for j, mm in enumerate(m) if mm],
                        [ys[j] for j, mm in enumerate(m) if mm],
                        label=c, alpha=0.7, s=18, color=palette[i % len(palette)],
                    )
                ax.legend(title=color_by, fontsize=8, loc="best")
        else:
            ax.scatter(xs, ys, alpha=0.6, s=18)

        ax.set_xlabel("tSNE_1"); ax.set_ylabel("tSNE_2")
        ax.set_title(title)
        fig.tight_layout()

        out_path = ctx.out_dir / f"{self.id}.png"
        fig.savefig(out_path, format="png", dpi=DEFAULT_DPI, bbox_inches="tight")
        plt.close(fig)

        return {
            "kind": "image",
            "format": "png",
            "path": str(out_path),
            "chart": "scatter",
            "title": title,
            "rows_plotted": df.height,
        }


step = TSNEStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

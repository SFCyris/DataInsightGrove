"""DBSCAN clustering step.

Density-based clustering — finds clusters of arbitrary shape and labels
low-density points as noise (cluster id = -1). Adds a cluster column and
renders a scatter (PCA-projected if >2 features).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.engine.chart_defaults import DEFAULT_DPI, DEFAULT_FIGSIZE


def _is_numeric(dtype: pl.DataType) -> bool:
    name = str(dtype).lower()
    return any(t in name for t in ("int", "float", "double", "decimal"))


class DBSCANStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.cluster import DBSCAN
        from sklearn.preprocessing import StandardScaler

        df = inputs["in"]
        cols = params.get("columns") or [c for c, t in df.schema.items() if _is_numeric(t)]
        cols = [c for c in cols if c in df.columns]
        if len(cols) < 1:
            raise ValueError("dbscan: need at least 1 numeric feature column")

        eps = float(params.get("eps") or 0.5)
        min_samples = int(params.get("min_samples") or 5)
        out_col = (params.get("output_column") or "cluster").strip() or "cluster"

        from numpy import isfinite, full as np_full
        full_x = df.select(cols).to_numpy()
        mask = isfinite(full_x).all(axis=1)
        if mask.sum() < min_samples:
            raise ValueError(
                f"dbscan: only {int(mask.sum())} complete rows; need at least min_samples={min_samples}"
            )

        x = full_x[mask]
        if bool(params.get("scale", True)):
            x = StandardScaler().fit_transform(x)

        labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(x)

        full_labels = np_full(full_x.shape[0], -2, dtype=int)  # -2 → "row had nulls"
        full_labels[mask] = labels

        # -2 → null (not part of clustering); -1 → noise (kept as -1).
        s = pl.Series(out_col, full_labels).cast(pl.Int64)
        s = pl.when(s == -2).then(None).otherwise(s).alias(out_col)
        out = df.with_columns(s)

        n_clusters = int(len({int(c) for c in labels if c != -1}))
        n_noise = int((labels == -1).sum())

        artifacts: list[dict[str, Any]] = []
        artifacts.append({
            "kind": "stats",
            "label": "DBSCAN summary",
            "data": {
                "n_clusters": n_clusters,
                "n_noise_points": n_noise,
                "n_rows_used": int(mask.sum()),
                "eps": eps,
                "min_samples": min_samples,
            },
        })

        if bool(params.get("render", True)) and ctx is not None:
            artifacts.append(self._render(out, cols, out_col, params, ctx))

        return PolarsResult(output=out, artifacts=artifacts)

    def _render(
        self,
        df: pl.DataFrame,
        cols: list[str],
        out_col: str,
        params: dict[str, Any],
        ctx: PolarsContext,
    ) -> dict[str, Any]:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="whitegrid", context="notebook")

        title = params.get("title") or "DBSCAN clusters"
        sub = df.select([*cols, out_col]).drop_nulls(subset=cols)
        if sub.height > 50_000:
            sub = sub.sample(n=50_000, seed=42)

        if len(cols) == 1:
            xs = sub.get_column(cols[0]).to_numpy()
            ys = [0.0] * len(xs)
            xlabel, ylabel = cols[0], ""
        elif len(cols) == 2:
            xs = sub.get_column(cols[0]).to_numpy()
            ys = sub.get_column(cols[1]).to_numpy()
            xlabel, ylabel = cols[0], cols[1]
        else:
            from sklearn.decomposition import PCA
            from sklearn.preprocessing import StandardScaler
            x = sub.select(cols).to_numpy()
            if bool(params.get("scale", True)):
                x = StandardScaler().fit_transform(x)
            proj = PCA(n_components=2, random_state=42).fit_transform(x)
            xs = proj[:, 0]
            ys = proj[:, 1]
            xlabel, ylabel = "PC1", "PC2"

        labels_col = sub.get_column(out_col)
        labels = [None if v is None else int(v) for v in labels_col.to_list()]
        uniq = sorted({lbl for lbl in labels if lbl is not None})
        # Noise gets a fixed gray; clusters cycle through tab10.
        palette = sns.color_palette("tab10", n_colors=max(len([u for u in uniq if u != -1]), 3))

        fig, ax = plt.subplots(figsize=DEFAULT_FIGSIZE, dpi=DEFAULT_DPI)
        cluster_idx = 0
        for c in uniq:
            m = [lbl == c for lbl in labels]
            color = (0.6, 0.6, 0.6) if c == -1 else palette[cluster_idx % len(palette)]
            label = "noise" if c == -1 else f"cluster {c}"
            ax.scatter(
                [xs[i] for i, mm in enumerate(m) if mm],
                [ys[i] for i, mm in enumerate(m) if mm],
                label=label, alpha=0.7, s=18, color=color,
            )
            if c != -1:
                cluster_idx += 1
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        ax.legend(fontsize=8, loc="best")
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
            "rows_plotted": sub.height,
        }


step = DBSCANStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

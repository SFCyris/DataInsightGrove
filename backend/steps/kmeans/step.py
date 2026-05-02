"""K-Means clustering step.

Adds a cluster-id column to the input data and renders a 2-D scatter showing
the cluster assignments. For inputs with >2 numeric columns, PCA is used for
the visualization only — the clustering itself runs on the original space.
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


class KMeansStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        df = inputs["in"]
        cols = params.get("columns") or [c for c, t in df.schema.items() if _is_numeric(t)]
        cols = [c for c in cols if c in df.columns]
        if len(cols) < 1:
            raise ValueError("kmeans: need at least 1 numeric feature column")

        k = int(params.get("k") or 4)
        seed = int(params.get("seed") or 42)
        out_col = (params.get("output_column") or "cluster").strip() or "cluster"

        # Use only complete rows for fitting; assign by predicting on full data,
        # leaving null assignments where any feature is missing.
        from numpy import isfinite, full as np_full
        full_x = df.select(cols).to_numpy()
        mask = isfinite(full_x).all(axis=1)
        if mask.sum() < k:
            raise ValueError(
                f"kmeans: only {int(mask.sum())} complete rows for k={k}; need at least {k}"
            )

        scaler = None
        if bool(params.get("scale", True)):
            scaler = StandardScaler().fit(full_x[mask])
            x_fit = scaler.transform(full_x[mask])
        else:
            x_fit = full_x[mask]

        km = KMeans(n_clusters=k, n_init=10, random_state=seed)
        km.fit(x_fit)

        # Predict on the full data (where mask is true).
        if scaler is not None:
            x_full = full_x.copy()
            x_full[mask] = scaler.transform(full_x[mask])
        else:
            x_full = full_x

        labels = np_full(full_x.shape[0], -1, dtype=int)
        labels[mask] = km.predict(x_full[mask])

        # Polars: -1 → null; everything else → that integer cluster id.
        labels_series = pl.Series(out_col, labels).cast(pl.Int64)
        labels_series = (
            pl.when(labels_series == -1).then(None).otherwise(labels_series).alias(out_col)
        )
        out = df.with_columns(labels_series)

        artifacts: list[dict[str, Any]] = []
        artifacts.append({
            "kind": "stats",
            "label": f"K-Means (k={k})",
            "data": {
                "k": k,
                "n_rows_used": int(mask.sum()),
                "inertia": float(km.inertia_),
                "centroids_shape": list(km.cluster_centers_.shape),
                "cluster_sizes": pl.Series(labels[mask]).value_counts().sort("count", descending=True).to_dicts(),
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

        title = params.get("title") or "K-Means clusters"
        sub = df.select([*cols, out_col]).drop_nulls()
        if sub.height > 50_000:
            sub = sub.sample(n=50_000, seed=42)
        if sub.height == 0:
            fig, ax = plt.subplots(figsize=(6, 4), dpi=144)
            ax.text(0.5, 0.5, "no rows", ha="center", va="center")
            out_path = ctx.out_dir / f"{self.id}.png"
            fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
            plt.close(fig)
            return {"kind": "image", "format": "png", "path": str(out_path), "chart": "scatter", "title": title}

        # If 2 features → plot directly. If 1 → strip plot. If >2 → PCA project.
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

        labels = sub.get_column(out_col).cast(pl.Int64).to_list()
        uniq = sorted(set(labels))
        palette = sns.color_palette("tab10", n_colors=max(len(uniq), 3))

        fig, ax = plt.subplots(figsize=(7, 5), dpi=144)
        for c in uniq:
            m = [lbl == c for lbl in labels]
            ax.scatter(
                [xs[i] for i, mm in enumerate(m) if mm],
                [ys[i] for i, mm in enumerate(m) if mm],
                label=f"cluster {c}", alpha=0.75, s=20, color=palette[uniq.index(c) % len(palette)],
            )
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        ax.legend(fontsize=8, loc="best")
        ax.set_title(title)
        fig.tight_layout()

        out_path = ctx.out_dir / f"{self.id}.png"
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)

        return {
            "kind": "image",
            "format": "png",
            "path": str(out_path),
            "chart": "scatter",
            "title": title,
            "rows_plotted": sub.height,
        }


step = KMeansStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""dendrogram — hierarchical clustering tree via scipy."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class DendrogramStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from scipy.cluster.hierarchy import linkage, dendrogram as sp_dendrogram
        from scipy.spatial.distance import pdist
        import numpy as np

        df = inputs["in"]
        vec_col = params["vectorColumn"]
        label_col = params.get("labelColumn")
        method = (params.get("method") or "ward").lower()
        metric = (params.get("metric") or "euclidean").lower()
        title = params.get("title") or "Dendrogram"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1600); height = int(params.get("height") or 800)

        if vec_col not in df.columns:
            raise ValueError(f"dendrogram: vectorColumn {vec_col!r} not found")

        vectors = np.asarray(df[vec_col].to_list(), dtype=float)
        if vectors.ndim != 2:
            raise ValueError("dendrogram: vector column rows must all have the same length")
        if vectors.shape[0] < 2:
            raise ValueError("dendrogram: need at least 2 rows to cluster")

        labels = ([str(v) for v in df[label_col].to_list()]
                   if label_col and label_col in df.columns
                   else [str(i) for i in range(vectors.shape[0])])

        # ward requires euclidean distances; if user picked non-euclidean
        # with ward, demote to 'complete' which accepts any metric.
        if method == "ward" and metric != "euclidean":
            method = "complete"

        dists = pdist(vectors, metric={"manhattan": "cityblock"}.get(metric, metric))
        Z = linkage(dists, method=method)

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        sp_dendrogram(Z, labels=labels, ax=ax, leaf_rotation=45, color_threshold=0.7 * max(Z[:, 2]))
        ax.set_title(title); ax.set_ylabel(f"{metric} distance")

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "dendrogram",
            "title": title, "method": method, "metric": metric, "n_observations": vectors.shape[0],
        }])


step = DendrogramStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

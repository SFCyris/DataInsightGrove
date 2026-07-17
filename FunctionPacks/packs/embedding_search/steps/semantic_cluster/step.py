from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _coerce_embeddings(series: pl.Series):
    import numpy as np
    sample = series[0]
    if isinstance(sample, str):
        return np.array([json.loads(s) for s in series.to_list()], dtype=float)
    return np.array(series.to_list(), dtype=float)


class SemanticClusterStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.cluster import AgglomerativeClustering

        df = inputs["in"]
        emb_col = params["embedding_column"]
        n_clusters = int(params.get("n_clusters", 8))
        linkage = params.get("linkage", "average")
        out_col = params.get("output_column", "cluster")

        X = _coerce_embeddings(df[emb_col])
        if X.shape[0] < n_clusters:
            raise ValueError(
                f"semantic_cluster: n_clusters ({n_clusters}) must be ≤ n_rows ({X.shape[0]})",
            )
        # Ward requires euclidean. Otherwise default to cosine.
        metric = "euclidean" if linkage == "ward" else "cosine"
        clf = AgglomerativeClustering(
            n_clusters=n_clusters, linkage=linkage, metric=metric,
        )
        labels = clf.fit_predict(X)
        return PolarsResult(output=df.with_columns(pl.Series(name=out_col, values=labels.tolist())))


step = SemanticClusterStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

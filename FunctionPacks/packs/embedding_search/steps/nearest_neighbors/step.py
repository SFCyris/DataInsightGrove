from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _coerce_embeddings(series: pl.Series) -> Any:
    import numpy as np
    # Polars list/array column → 2-D ndarray.
    # If the column is JSON text instead (came from CSV), parse first.
    sample = series[0]
    if isinstance(sample, str):
        return np.array([json.loads(s) for s in series.to_list()], dtype=float)
    return np.array(series.to_list(), dtype=float)


class NearestNeighborsStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.neighbors import NearestNeighbors
        import numpy as np

        df = inputs["in"]
        emb_col = params["embedding_column"]
        label_col = params.get("label_column")
        k = int(params.get("k", 5))
        metric = params.get("metric", "cosine")

        X = _coerce_embeddings(df[emb_col])
        if X.ndim != 2:
            raise ValueError(f"nearest_neighbors: embedding column must be 2-D, got shape {X.shape}")

        n = X.shape[0]
        # +1 because the closest match for each row is itself
        nn = NearestNeighbors(n_neighbors=min(k + 1, n), metric=metric)
        nn.fit(X)
        distances, indices = nn.kneighbors(X)

        labels = df[label_col].to_list() if label_col else None
        rows: list[dict[str, Any]] = []
        for src_idx in range(n):
            for rank, (neighbour_idx, dist) in enumerate(zip(indices[src_idx], distances[src_idx])):
                if neighbour_idx == src_idx:  # skip self
                    continue
                row: dict[str, Any] = {
                    "source_idx": int(src_idx),
                    "neighbour_idx": int(neighbour_idx),
                    "distance": float(dist),
                    "rank": int(rank if rank < indices[src_idx].tolist().index(src_idx) else rank - 1),
                }
                if labels is not None:
                    row["source_label"] = labels[src_idx]
                    row["neighbour_label"] = labels[int(neighbour_idx)]
                rows.append(row)
                if rank >= k:
                    break
        return PolarsResult(output=pl.DataFrame(rows))


step = NearestNeighborsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

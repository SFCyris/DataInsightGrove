"""top_k_similar — per-row top-K nearest-neighbour search.

scipy.spatial.distance.cdist computes the full N×N pairwise matrix in
vectorised C, then numpy.argpartition picks each row's K-best in
O(N log K) time. Excluding self (the default) just sets the diagonal
to +inf for distance metrics or -inf for similarity metrics before
the partition.

Output: two new array columns per row.
  top_k_indices — array of K ids (integers or label values)
  top_k_scores  — array of K similarity / distance values, sorted
                  best-first
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy.spatial.distance import cdist

from dig.engine.step import PolarsContext, PolarsResult, Step


_HIGHER_IS_BETTER = {"cosine", "dot"}
_LOWER_IS_BETTER = {"euclidean"}


class TopKSimilarStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        vec_col = params["vectorColumn"]
        if vec_col not in df.columns:
            raise ValueError(
                f"top_k_similar: vector column {vec_col!r} not found",
            )
        k = int(params.get("k", 5))
        metric = (params.get("metric") or "cosine").lower()
        include_self = bool(params.get("includeSelf", False))
        label_col = params.get("labelColumn")
        idx_name = params.get("indicesColumn") or "top_k_indices"
        sco_name = params.get("scoresColumn") or "top_k_scores"

        n = df.height
        if n == 0:
            return PolarsResult(output=df)
        if k > n:
            k = n

        vectors = np.array(df[vec_col].to_list(), dtype=float)
        if vectors.ndim != 2:
            raise ValueError(
                f"top_k_similar: column {vec_col!r} is not a vector "
                "column (expected list of numbers per row, all rows the "
                "same length).",
            )

        # Compute the score / distance matrix.
        if metric == "dot":
            # Higher = more similar; not in scipy, hand-roll.
            scores = vectors @ vectors.T
            higher_is_better = True
        elif metric == "cosine":
            # scipy.cdist returns cosine *distance* (1 - similarity).
            # Convert to similarity so 1.0 = identical and the "best"
            # neighbour has the highest number.
            scores = 1.0 - cdist(vectors, vectors, metric="cosine")
            higher_is_better = True
        else:  # euclidean
            scores = cdist(vectors, vectors, metric="euclidean")
            higher_is_better = False

        # Mask self if requested. For higher-is-better metrics push
        # self to -inf so it falls out of the partition; for lower
        # push to +inf.
        if not include_self:
            mask_value = -np.inf if higher_is_better else np.inf
            np.fill_diagonal(scores, mask_value)

        # Per-row top-K. argpartition is O(N) per row; final sort is
        # O(K log K).
        if higher_is_better:
            # Want the K LARGEST per row.
            part = np.argpartition(-scores, k - 1, axis=1)[:, :k]
        else:
            part = np.argpartition(scores, k - 1, axis=1)[:, :k]

        # Sort the K within each row best-first.
        labels = (
            df[label_col].to_list() if label_col and label_col in df.columns
            else list(range(n))
        )
        topk_idx: list[list] = []
        topk_sco: list[list[float]] = []
        for i in range(n):
            row_idx = part[i]
            row_scores = scores[i, row_idx]
            order = np.argsort(-row_scores) if higher_is_better else np.argsort(row_scores)
            sorted_idx = row_idx[order]
            sorted_sco = row_scores[order]
            topk_idx.append([labels[j] for j in sorted_idx.tolist()])
            topk_sco.append(sorted_sco.tolist())

        out_df = df.with_columns([
            pl.Series(idx_name, topk_idx),
            pl.Series(sco_name, topk_sco),
        ])
        return PolarsResult(output=out_df)


step = TopKSimilarStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

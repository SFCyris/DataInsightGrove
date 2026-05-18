"""distance_matrix — pairwise distances between every pair of rows.

scipy.spatial.distance.cdist is the workhorse: vectorised C implementation
across N×N row pairs. For N up to ~10k this runs in seconds; the
``maxRows`` param caps N² growth so a careless click can't OOM the worker.

Output shape:
  - long   → (row_i, row_j, distance) — natural input for clustering /
              MDS / nearest-neighbour follow-ups
  - square → N rows, N columns; the cell at (i, j) is the distance
              from row i to row j
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy.spatial.distance import cdist

from dig.engine.step import PolarsContext, PolarsResult, Step


_METRIC_MAP = {
    "euclidean": "euclidean",
    "cosine": "cosine",
    "manhattan": "cityblock",
    "chebyshev": "chebyshev",
}


class DistanceMatrixStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        vec_col = params["vectorColumn"]
        metric = (params.get("metric") or "euclidean").lower()
        fmt = (params.get("outputFormat") or "long").lower()
        label_col = params.get("labelColumn")
        max_rows = int(params.get("maxRows") or 1000)

        if vec_col not in df.columns:
            raise ValueError(
                f"distance_matrix: vector column {vec_col!r} not found",
            )

        if df.height > max_rows:
            raise ValueError(
                f"distance_matrix: input has {df.height} rows, exceeds "
                f"maxRows cap of {max_rows}. Pre-filter or raise the cap "
                "consciously — N² output grows fast.",
            )

        # Materialise the vector column as a 2-D float ndarray.
        # Polars stores list-of-double as List dtype; .to_list() then
        # numpy.array gives the (N, D) matrix scipy needs.
        vectors = np.array(df[vec_col].to_list(), dtype=float)
        if vectors.ndim != 2:
            raise ValueError(
                f"distance_matrix: column {vec_col!r} is not a vector "
                "column (expected list of numbers per row, all rows the "
                "same length).",
            )
        scipy_metric = _METRIC_MAP.get(metric, "euclidean")
        d = cdist(vectors, vectors, metric=scipy_metric)

        # Labels: either user-picked column or integer index.
        if label_col and label_col in df.columns:
            labels = df[label_col].to_list()
        else:
            labels = list(range(df.height))

        if fmt == "square":
            # Each row = labelled by labels[i], columns = labels[j] as
            # strings (Polars columns must be strings).
            cols: dict[str, list] = {"row": labels}
            for j, lab in enumerate(labels):
                cols[str(lab)] = d[:, j].tolist()
            out_df = pl.DataFrame(cols)
        else:  # long form
            n = len(labels)
            i_idx = np.repeat(np.arange(n), n)
            j_idx = np.tile(np.arange(n), n)
            out_df = pl.DataFrame({
                "row_i": [labels[i] for i in i_idx.tolist()],
                "row_j": [labels[j] for j in j_idx.tolist()],
                "distance": d.flatten().tolist(),
            })

        return PolarsResult(output=out_df)


step = DistanceMatrixStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

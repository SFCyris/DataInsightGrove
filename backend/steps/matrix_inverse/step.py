"""matrix_inverse — square-matrix inversion with both input shapes.

column_grid mode treats N picked columns × M rows as an M×N matrix and
requires M == N (square). The output frame is the inverse, in the same
M×N shape, with column names preserved.

nested_list mode applies inversion per row to a list-of-list column.
The pseudoinverse option swaps numpy.linalg.inv for numpy.linalg.pinv
so rank-deficient inputs return a least-squares pseudoinverse instead
of raising LinAlgError.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _invert(matrix: np.ndarray, use_pinv: bool) -> np.ndarray:
    if use_pinv:
        return np.linalg.pinv(matrix)
    try:
        return np.linalg.inv(matrix)
    except np.linalg.LinAlgError as e:
        raise ValueError(
            f"matrix_inverse: matrix is singular ({e}). "
            "Enable Pseudoinverse fallback for a least-squares pinv.",
        ) from e


class MatrixInverseStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        mode = (params.get("mode") or "column_grid").lower()
        use_pinv = bool(params.get("pseudoinverse", False))

        if mode == "column_grid":
            cols = params.get("valueColumns") or []
            if not cols:
                raise ValueError(
                    "matrix_inverse: column_grid mode needs valueColumns",
                )
            missing = [c for c in cols if c not in df.columns]
            if missing:
                raise ValueError(
                    f"matrix_inverse: columns not found: {missing}",
                )
            mat = df.select(cols).to_numpy()
            if mat.shape[0] != mat.shape[1]:
                raise ValueError(
                    f"matrix_inverse: matrix must be square; got "
                    f"{mat.shape[0]}×{mat.shape[1]} "
                    f"({mat.shape[0]} rows, {mat.shape[1]} columns).",
                )
            inv = _invert(mat, use_pinv)
            out_df = pl.DataFrame({c: inv[:, i].tolist() for i, c in enumerate(cols)})
            return PolarsResult(output=out_df)

        if mode == "nested_list":
            src = params.get("nestedListColumn")
            if not src:
                raise ValueError(
                    "matrix_inverse: nested_list mode needs nestedListColumn",
                )
            if src not in df.columns:
                raise ValueError(
                    f"matrix_inverse: column {src!r} not found",
                )
            out_name = params.get("outputColumn") or "inverse"
            inverted: list[list[list[float]] | None] = []
            for cell in df[src].to_list():
                if cell is None:
                    inverted.append(None)
                    continue
                arr = np.array(cell, dtype=float)
                if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
                    raise ValueError(
                        f"matrix_inverse: each cell must be a square matrix; "
                        f"got shape {arr.shape}.",
                    )
                inverted.append(_invert(arr, use_pinv).tolist())
            out_df = df.with_columns(pl.Series(out_name, inverted))
            return PolarsResult(output=out_df)

        raise ValueError(f"matrix_inverse: unknown mode {mode!r}")


step = MatrixInverseStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""matrix_transpose — supports two input shapes.

column_grid: the user picked N columns; we treat them as an M×N matrix
(M = row count). Transpose flips to N×M; the output frame has M columns
named col_0..col_{M-1} and N rows. The original (non-value) columns are
NOT carried — the output is the transposed matrix only, so subsequent
steps can operate on it cleanly.

nested_list: each row already carries a full matrix as a list-of-list
column. Transpose is applied per row; the row count is preserved; a
new column carries each row's transpose. Other input columns are kept.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class MatrixTransposeStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        mode = (params.get("mode") or "column_grid").lower()

        if mode == "column_grid":
            cols = params.get("valueColumns") or []
            if not cols:
                raise ValueError(
                    "matrix_transpose: column_grid mode needs valueColumns",
                )
            missing = [c for c in cols if c not in df.columns]
            if missing:
                raise ValueError(
                    f"matrix_transpose: columns not found: {missing}",
                )
            mat = df.select(cols).to_numpy()
            t = mat.T  # shape (N, M)
            out_cols = {f"col_{i}": t[:, i].tolist() for i in range(t.shape[1])}
            out_df = pl.DataFrame(out_cols)
            return PolarsResult(output=out_df)

        if mode == "nested_list":
            src = params.get("nestedListColumn")
            if not src:
                raise ValueError(
                    "matrix_transpose: nested_list mode needs nestedListColumn",
                )
            if src not in df.columns:
                raise ValueError(
                    f"matrix_transpose: column {src!r} not found",
                )
            out_name = params.get("outputColumn") or "transposed"

            transposed: list[list[list[float]] | None] = []
            for cell in df[src].to_list():
                if cell is None:
                    transposed.append(None)
                    continue
                arr = np.array(cell, dtype=float)
                if arr.ndim != 2:
                    # Treat 1-D as a row vector → transpose to column.
                    arr = arr.reshape(1, -1)
                transposed.append(arr.T.tolist())
            out_df = df.with_columns(pl.Series(out_name, transposed))
            return PolarsResult(output=out_df)

        raise ValueError(f"matrix_transpose: unknown mode {mode!r}")


step = MatrixTransposeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

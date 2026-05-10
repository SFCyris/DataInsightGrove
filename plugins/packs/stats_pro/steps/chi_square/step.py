from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ChiSquareStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from scipy import stats

        df = inputs["in"]
        row, col = params["row"], params["col"]
        for c in (row, col):
            if c not in df.columns:
                raise ValueError(f"chi_square: column {c!r} not in input")

        contingency = (
            df.select([row, col])
              .drop_nulls()
              .group_by([row, col])
              .agg(pl.len().alias("n"))
              .pivot(values="n", index=row, on=col)
              .fill_null(0)
        )
        # Drop the row-label column for the test; keep it for context.
        labels = contingency[row].to_list()
        matrix = contingency.drop(row).to_numpy()
        if matrix.shape[0] < 2 or matrix.shape[1] < 2:
            raise ValueError(
                f"chi_square: contingency table must be at least 2x2, got {matrix.shape}",
            )

        chi2, p, dof, _expected = stats.chi2_contingency(matrix)
        n = int(matrix.sum())
        # Cramér's V — effect size for chi².
        k = min(matrix.shape) - 1
        cramers_v = float((chi2 / (n * k)) ** 0.5) if n > 0 and k > 0 else 0.0

        out = pl.DataFrame([{
            "row_column": row,
            "column_column": col,
            "n": n,
            "chi_squared": float(chi2),
            "p_value": float(p),
            "df": int(dof),
            "cramers_v": cramers_v,
            "row_levels": ", ".join(str(x) for x in labels[:10]),
        }])
        return PolarsResult(output=out)


step = ChiSquareStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

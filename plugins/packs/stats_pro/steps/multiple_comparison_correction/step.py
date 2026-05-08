from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class MultipleComparisonCorrectionStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from statsmodels.stats.multitest import multipletests

        df = inputs["in"]
        p_col = params["p_column"]
        method = params.get("method", "fdr_bh")
        alpha = float(params.get("alpha", 0.05))

        if p_col not in df.columns:
            raise ValueError(f"multiple_comparison_correction: column {p_col!r} not in input")

        p_values = df[p_col].to_numpy()
        # multipletests doesn't tolerate NaN — flag them as non-significant
        # and pass only the finite ones through the adjuster.
        import numpy as np
        finite_mask = np.isfinite(p_values)
        adjusted = np.full_like(p_values, np.nan, dtype=float)
        rejected = np.zeros_like(p_values, dtype=bool)
        if finite_mask.any():
            r, p_adj, _, _ = multipletests(p_values[finite_mask], alpha=alpha, method=method)
            adjusted[finite_mask] = p_adj
            rejected[finite_mask] = r

        out = df.with_columns([
            pl.Series(name=f"{p_col}_adjusted", values=adjusted.tolist()),
            pl.Series(name=f"{p_col}_significant", values=rejected.tolist()),
        ])
        return PolarsResult(output=out)


step = MultipleComparisonCorrectionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

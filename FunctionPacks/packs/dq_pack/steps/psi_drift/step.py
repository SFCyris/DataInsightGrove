from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _interpret(psi: float) -> str:
    if psi < 0.1:
        return "stable"
    if psi < 0.25:
        return "moderate drift"
    return "significant drift"


class PsiDriftStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import numpy as np

        df = inputs["in"]
        value_col = params["value"]
        partition_col = params["partition"]
        n_bins = int(params.get("n_bins", 10))

        clean = df.select([value_col, partition_col]).drop_nulls()
        partitions = clean[partition_col].unique().to_list()
        if len(partitions) != 2:
            raise ValueError(
                f"psi_drift: partition must have 2 distinct values, found {len(partitions)}",
            )
        a_label, b_label = partitions
        a = clean.filter(pl.col(partition_col) == a_label)[value_col].to_numpy()
        b = clean.filter(pl.col(partition_col) == b_label)[value_col].to_numpy()
        if len(a) < n_bins or len(b) < n_bins:
            raise ValueError(
                f"psi_drift: each partition needs at least n_bins ({n_bins}) observations",
            )

        # Use baseline (a) quantiles as bin edges so unequal sample sizes are fair.
        edges = np.unique(np.quantile(a, np.linspace(0, 1, n_bins + 1)))
        if len(edges) < 3:
            raise ValueError("psi_drift: too few unique values in baseline to form bins")
        edges[0] -= 1e-9
        edges[-1] += 1e-9
        a_hist, _ = np.histogram(a, bins=edges)
        b_hist, _ = np.histogram(b, bins=edges)
        a_pct = a_hist / max(a_hist.sum(), 1)
        b_pct = b_hist / max(b_hist.sum(), 1)
        # Avoid log(0): substitute tiny epsilon
        eps = 1e-9
        psi_per_bin = (b_pct - a_pct) * np.log((b_pct + eps) / (a_pct + eps))
        psi = float(psi_per_bin.sum())

        out = pl.DataFrame([{
            "value_column": value_col,
            "partition_column": partition_col,
            "baseline_label": str(a_label),
            "current_label": str(b_label),
            "n_baseline": int(len(a)),
            "n_current": int(len(b)),
            "n_bins": int(len(edges) - 1),
            "psi": psi,
            "interpretation": _interpret(psi),
        }])
        return PolarsResult(output=out)


step = PsiDriftStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

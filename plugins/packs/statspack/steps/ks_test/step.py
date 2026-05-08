"""Two-sample Kolmogorov-Smirnov test."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class KsTestStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from scipy import stats

        df = inputs["in"]
        value_col = params["value"]
        group_col = params["group"]
        alternative = params.get("alternative", "two-sided")

        if value_col not in df.columns:
            raise ValueError(f"ks_test: value column {value_col!r} not in input")
        if group_col not in df.columns:
            raise ValueError(f"ks_test: group column {group_col!r} not in input")

        clean = df.select([group_col, value_col]).drop_nulls()
        if clean.height == 0:
            raise ValueError("ks_test: no non-null rows after filtering")

        groups = sorted(clean[group_col].unique().to_list(), key=lambda x: (x is None, str(x)))
        if len(groups) != 2:
            raise ValueError(
                f"ks_test: group column must have exactly 2 distinct values, "
                f"found {len(groups)}: {groups[:5]}",
            )
        a_label, b_label = groups
        a_vals = clean.filter(pl.col(group_col) == a_label)[value_col].to_numpy()
        b_vals = clean.filter(pl.col(group_col) == b_label)[value_col].to_numpy()
        if len(a_vals) < 2 or len(b_vals) < 2:
            raise ValueError(
                f"ks_test: each group needs ≥2 observations "
                f"(got {len(a_vals)} and {len(b_vals)})",
            )

        result = stats.ks_2samp(a_vals, b_vals, alternative=alternative)

        out = pl.DataFrame([{
            "value_column": value_col,
            "group_column": group_col,
            "group_a": str(a_label),
            "group_b": str(b_label),
            "n_a": int(len(a_vals)),
            "n_b": int(len(b_vals)),
            "ks_statistic": float(result.statistic),
            "p_value": float(result.pvalue),
            "alternative": alternative,
            "test": "Kolmogorov-Smirnov 2-sample",
        }])
        return PolarsResult(output=out)


step = KsTestStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

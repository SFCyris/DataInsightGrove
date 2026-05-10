from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class MannWhitneyStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from scipy import stats

        df = inputs["in"]
        value, group = params["value"], params["group"]
        alternative = params.get("alternative", "two-sided")

        clean = df.select([group, value]).drop_nulls()
        groups = sorted(clean[group].unique().to_list(), key=lambda x: (x is None, str(x)))
        if len(groups) != 2:
            raise ValueError(f"mann_whitney: need exactly 2 groups, found {len(groups)}")

        a = clean.filter(pl.col(group) == groups[0])[value].to_numpy()
        b = clean.filter(pl.col(group) == groups[1])[value].to_numpy()
        if len(a) < 2 or len(b) < 2:
            raise ValueError(f"mann_whitney: each group needs ≥2 observations")

        result = stats.mannwhitneyu(a, b, alternative=alternative)
        # Rank-biserial correlation effect size
        n_a, n_b = len(a), len(b)
        rb = 1.0 - (2.0 * float(result.statistic)) / (n_a * n_b)

        out = pl.DataFrame([{
            "value_column": value,
            "group_column": group,
            "group_a": str(groups[0]),
            "group_b": str(groups[1]),
            "n_a": int(n_a),
            "n_b": int(n_b),
            "median_a": float(pl.Series(a).median() or 0.0),
            "median_b": float(pl.Series(b).median() or 0.0),
            "u_statistic": float(result.statistic),
            "p_value": float(result.pvalue),
            "rank_biserial_corr": rb,
            "alternative": alternative,
            "test": "Mann-Whitney U",
        }])
        return PolarsResult(output=out)


step = MannWhitneyStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

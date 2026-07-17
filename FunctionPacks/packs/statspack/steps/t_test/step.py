"""Two-sample independent t-test (Welch's by default).

The pack-shipped steps live under <repo>/plugins/packs/<pack>/steps/<id>/
at runtime. The Python contract is identical to a built-in step: subclass
dig.engine.step.Step, implement execute_polars(...), instantiate `step`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class TTestStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from scipy import stats  # local import — keeps registry boot fast

        df = inputs["in"]
        value_col = params["value"]
        group_col = params["group"]
        alternative = params.get("alternative", "two-sided")
        equal_var = bool(params.get("equal_var", False))

        if value_col not in df.columns:
            raise ValueError(f"t_test: value column {value_col!r} not in input")
        if group_col not in df.columns:
            raise ValueError(f"t_test: group column {group_col!r} not in input")

        # Drop rows with null in either column — t-test wants paired
        # complete cases; surfacing that as silent NaN in the output
        # would mask the real sample size.
        clean = df.select([group_col, value_col]).drop_nulls()
        if clean.height == 0:
            raise ValueError("t_test: no non-null rows after filtering")

        groups = sorted(clean[group_col].unique().to_list(), key=lambda x: (x is None, str(x)))
        if len(groups) != 2:
            raise ValueError(
                f"t_test: group column must have exactly 2 distinct values, "
                f"found {len(groups)}: {groups[:5]}",
            )
        a_label, b_label = groups
        a_vals = clean.filter(pl.col(group_col) == a_label)[value_col].to_numpy()
        b_vals = clean.filter(pl.col(group_col) == b_label)[value_col].to_numpy()
        if len(a_vals) < 2 or len(b_vals) < 2:
            raise ValueError(
                f"t_test: each group needs ≥2 observations "
                f"(got {len(a_vals)} and {len(b_vals)})",
            )

        result = stats.ttest_ind(
            a_vals, b_vals,
            equal_var=equal_var,
            alternative=alternative,
            nan_policy="omit",
        )

        out = pl.DataFrame([{
            "value_column": value_col,
            "group_column": group_col,
            "group_a": str(a_label),
            "group_b": str(b_label),
            "n_a": int(len(a_vals)),
            "n_b": int(len(b_vals)),
            "mean_a": float(a_vals.mean()),
            "mean_b": float(b_vals.mean()),
            "diff_means": float(a_vals.mean() - b_vals.mean()),
            "t_statistic": float(result.statistic),
            "p_value": float(result.pvalue),
            "df": float(getattr(result, "df", float("nan"))),
            "alternative": alternative,
            "test": "Welch's t" if not equal_var else "Student's t",
        }])
        return PolarsResult(output=out)


step = TTestStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

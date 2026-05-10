from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class AnovaStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from scipy import stats
        import numpy as np

        df = inputs["in"]
        value, group = params["value"], params["group"]
        if value not in df.columns or group not in df.columns:
            raise ValueError(f"anova: missing column ({value!r} or {group!r})")

        clean = df.select([group, value]).drop_nulls()
        if clean.height == 0:
            raise ValueError("anova: no non-null rows")

        groups = sorted(clean[group].unique().to_list(), key=lambda x: (x is None, str(x)))
        if len(groups) < 2:
            raise ValueError(f"anova: need ≥2 groups, found {len(groups)}")

        samples = [
            clean.filter(pl.col(group) == g)[value].to_numpy()
            for g in groups
        ]
        for i, s in enumerate(samples):
            if len(s) < 2:
                raise ValueError(f"anova: group {groups[i]!r} has fewer than 2 observations")

        f_stat, p_value = stats.f_oneway(*samples)

        all_vals = np.concatenate(samples)
        grand_mean = float(all_vals.mean())
        ss_between = float(sum(len(s) * (s.mean() - grand_mean) ** 2 for s in samples))
        ss_within = float(sum(((s - s.mean()) ** 2).sum() for s in samples))
        ss_total = ss_between + ss_within
        eta_squared = ss_between / ss_total if ss_total > 0 else 0.0

        out = pl.DataFrame([{
            "value_column": value,
            "group_column": group,
            "n_groups": len(groups),
            "n_total": int(len(all_vals)),
            "f_statistic": float(f_stat),
            "p_value": float(p_value),
            "ss_between": ss_between,
            "ss_within": ss_within,
            "eta_squared": eta_squared,
            "test": "One-way ANOVA",
        }])
        return PolarsResult(output=out)


step = AnovaStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

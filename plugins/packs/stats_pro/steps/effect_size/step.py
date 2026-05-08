from __future__ import annotations

import json
from math import sqrt
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _cohens_d(a, b) -> float:
    n_a, n_b = len(a), len(b)
    s_a, s_b = a.std(ddof=1), b.std(ddof=1)
    pooled = sqrt(((n_a - 1) * s_a ** 2 + (n_b - 1) * s_b ** 2) / (n_a + n_b - 2))
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else 0.0


def _hedges_g(d: float, n_a: int, n_b: int) -> float:
    j = 1.0 - 3.0 / (4.0 * (n_a + n_b) - 9.0)
    return d * j


def _glass_delta(a, b) -> float:
    s_b = b.std(ddof=1)
    return float((a.mean() - b.mean()) / s_b) if s_b > 0 else 0.0


def _interpret_d(d: float) -> str:
    abs_d = abs(d)
    if abs_d < 0.2:
        return "negligible"
    if abs_d < 0.5:
        return "small"
    if abs_d < 0.8:
        return "medium"
    return "large"


class EffectSizeStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        value, group = params["value"], params["group"]
        clean = df.select([group, value]).drop_nulls()
        groups = sorted(clean[group].unique().to_list(), key=lambda x: (x is None, str(x)))
        if len(groups) != 2:
            raise ValueError(f"effect_size: need exactly 2 groups, found {len(groups)}")

        a = clean.filter(pl.col(group) == groups[0])[value].to_numpy()
        b = clean.filter(pl.col(group) == groups[1])[value].to_numpy()
        if len(a) < 2 or len(b) < 2:
            raise ValueError("effect_size: each group needs ≥2 observations")

        d = _cohens_d(a, b)
        g = _hedges_g(d, len(a), len(b))
        delta = _glass_delta(a, b)

        out = pl.DataFrame([{
            "value_column": value,
            "group_column": group,
            "group_a": str(groups[0]),
            "group_b": str(groups[1]),
            "n_a": int(len(a)),
            "n_b": int(len(b)),
            "mean_a": float(a.mean()),
            "mean_b": float(b.mean()),
            "cohens_d": d,
            "hedges_g": g,
            "glass_delta": delta,
            "interpretation": _interpret_d(d),
        }])
        return PolarsResult(output=out)


step = EffectSizeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

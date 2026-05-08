from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


_STATS = {
    "mean":   lambda x: float(x.mean()),
    "median": lambda x: float((__import__("numpy").median(x))),
    "std":    lambda x: float(x.std(ddof=1)),
    "iqr":    lambda x: float((__import__("numpy").percentile(x, 75)) - __import__("numpy").percentile(x, 25)),
}


class BootstrapCIStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import numpy as np

        df = inputs["in"]
        value = params["value"]
        statistic = params.get("statistic", "mean")
        confidence = float(params.get("confidence", 0.95))
        n_iter = int(params.get("n_iter", 2000))
        seed = int(params.get("seed", 0))

        if statistic not in _STATS:
            raise ValueError(f"bootstrap_ci: unknown statistic {statistic!r}")
        if value not in df.columns:
            raise ValueError(f"bootstrap_ci: column {value!r} not in input")

        x = df[value].drop_nulls().to_numpy()
        if len(x) < 2:
            raise ValueError(f"bootstrap_ci: need ≥2 non-null observations, got {len(x)}")

        rng = np.random.default_rng(seed if seed != 0 else None)
        stat_fn = _STATS[statistic]
        n = len(x)
        replicates = np.empty(n_iter, dtype=float)
        for i in range(n_iter):
            sample = rng.choice(x, size=n, replace=True)
            replicates[i] = stat_fn(sample)

        alpha = (1.0 - confidence) / 2.0
        lower = float(np.percentile(replicates, 100 * alpha))
        upper = float(np.percentile(replicates, 100 * (1 - alpha)))
        point = stat_fn(x)

        out = pl.DataFrame([{
            "value_column": value,
            "statistic": statistic,
            "n": int(n),
            "estimate": point,
            "ci_lower": lower,
            "ci_upper": upper,
            "ci_width": upper - lower,
            "confidence": confidence,
            "n_iterations": n_iter,
        }])
        return PolarsResult(output=out)


step = BootstrapCIStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

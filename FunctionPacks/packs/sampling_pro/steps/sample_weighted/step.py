"""sample_weighted — probability-proportional-to-weight sampling."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class SampleWeightedStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        wcol = params["weightColumn"]
        n = int(params.get("sampleSize", 1000))
        replace = bool(params.get("withReplacement", False))
        seed = int(params.get("seed", 42))
        weights = np.asarray(df[wcol].to_numpy(), dtype=float)
        weights = np.clip(weights, 0, None)
        if weights.sum() == 0:
            raise ValueError("sample_weighted: all weights are zero")
        probs = weights / weights.sum()
        n = min(n, df.height) if not replace else n
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(probs), size=n, replace=replace, p=probs)
        return PolarsResult(output=df[idx.tolist()])


step = SampleWeightedStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

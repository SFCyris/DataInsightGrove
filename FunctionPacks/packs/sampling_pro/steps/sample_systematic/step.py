"""sample_systematic — every Kth row after a random start."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class SampleSystematicStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        n = int(params.get("sampleSize", 1000))
        seed = int(params.get("seed", 42))
        if df.height <= n:
            return PolarsResult(output=df)
        k = max(1, df.height // n)
        rng = np.random.default_rng(seed)
        start = int(rng.integers(0, k))
        idx = list(range(start, df.height, k))[:n]
        return PolarsResult(output=df[idx])


step = SampleSystematicStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

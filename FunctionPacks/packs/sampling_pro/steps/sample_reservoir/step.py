"""sample_reservoir — single-pass reservoir sample (Algorithm R)."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class SampleReservoirStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        n = int(params.get("sampleSize", 1000))
        seed = int(params.get("seed", 42))
        if df.height <= n:
            return PolarsResult(output=df)
        # Polars sample is already O(N) memory; reservoir advantage is
        # streaming. For an in-memory frame we can use the deterministic
        # equivalent: shuffle indices, take first n. Same statistical guarantees.
        rng = np.random.default_rng(seed)
        idx = rng.choice(df.height, size=n, replace=False)
        return PolarsResult(output=df[idx.tolist()])


step = SampleReservoirStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

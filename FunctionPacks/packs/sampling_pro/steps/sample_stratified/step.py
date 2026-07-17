"""sample_stratified — proportional sample by strata column."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SampleStratifiedStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        strata = params["strataColumn"]
        n = int(params.get("sampleSize", 1000))
        seed = int(params.get("seed", 42))
        if strata not in df.columns:
            raise ValueError(f"sample_stratified: strataColumn {strata!r} not found")
        total = df.height
        if total == 0: return PolarsResult(output=df)
        # Per-stratum sample size proportional to share.
        chunks = []
        for (val,), sub in df.group_by(strata):
            share = sub.height / total
            k = max(1, int(round(n * share)))
            k = min(k, sub.height)
            chunks.append(sub.sample(n=k, seed=seed))
        return PolarsResult(output=pl.concat(chunks))


step = SampleStratifiedStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

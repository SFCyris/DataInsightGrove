"""sample_cluster — sample whole groups (clusters) at random."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class SampleClusterStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cluster = params["clusterColumn"]
        k = int(params.get("numClusters", 10))
        seed = int(params.get("seed", 42))
        if cluster not in df.columns:
            raise ValueError(f"sample_cluster: clusterColumn {cluster!r} not found")
        unique = df[cluster].unique().to_list()
        if len(unique) <= k:
            return PolarsResult(output=df)
        rng = np.random.default_rng(seed)
        chosen = rng.choice(unique, size=k, replace=False)
        out = df.filter(pl.col(cluster).is_in(chosen.tolist()))
        return PolarsResult(output=out)


step = SampleClusterStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

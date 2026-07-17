"""downsample_cic — N-stage CIC decimation filter."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class DownsampleCicStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        v = params["valueColumn"]; o = params["orderColumn"]
        R = int(params.get("decimationFactor", 10))
        N = int(params.get("stages", 3))
        sub = df.sort(o)
        x = np.asarray(sub[v].to_list(), dtype=float)
        # N-stage integrator.
        for _ in range(N):
            x = np.cumsum(x)
        # Decimate by R.
        x = x[::R]
        # N-stage comb at decimated rate.
        for _ in range(N):
            x = np.diff(x, prepend=0)
        # Normalise gain (R^N).
        gain = R ** N
        x = x / gain
        # Indices in original frame.
        idx = list(range(0, sub.height, R))[: len(x)]
        out = sub[idx].with_columns(pl.Series(f"{v}_decimated", x.tolist()))
        return PolarsResult(output=out)


step = DownsampleCicStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

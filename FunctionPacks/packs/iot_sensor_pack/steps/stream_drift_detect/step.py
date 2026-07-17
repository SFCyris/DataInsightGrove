"""stream_drift_detect — Page-Hinkley change-point flag per row."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class StreamDriftDetectStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        v = params["valueColumn"]; o = params["orderColumn"]
        threshold = float(params.get("threshold", 50.0))
        delta = float(params.get("delta", 0.005))
        sub = df.sort(o)
        values = sub[v].to_list()
        cumulative = 0.0; min_cum = 0.0; running_mean = 0.0
        flags = []
        for i, x in enumerate(values, start=1):
            running_mean = running_mean + (x - running_mean) / i
            cumulative += (x - running_mean - delta)
            min_cum = min(min_cum, cumulative)
            ph = cumulative - min_cum
            flags.append(bool(ph > threshold))
        out = sub.with_columns(pl.Series("drift_flag", flags))
        return PolarsResult(output=out)


step = StreamDriftDetectStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

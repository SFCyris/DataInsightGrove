"""multi_sensor_fusion — weighted-average sensor fusion."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class MultiSensorFusionStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        sensors = params.get("sensorColumns") or []
        weights_raw = (params.get("weights") or "").strip()
        out_col = params.get("outputColumn") or "fused"
        if weights_raw:
            weights = [float(w) for w in weights_raw.split(",")]
            if len(weights) != len(sensors):
                raise ValueError(
                    f"multi_sensor_fusion: {len(weights)} weights vs {len(sensors)} sensor columns"
                )
        else:
            weights = [1.0 / len(sensors)] * len(sensors)
        weight_sum = sum(weights) or 1.0
        weights = [w / weight_sum for w in weights]
        # Weighted sum.
        expr = sum((pl.col(c) * w for c, w in zip(sensors, weights)), pl.lit(0.0))
        return PolarsResult(output=df.with_columns(expr.alias(out_col)))


step = MultiSensorFusionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

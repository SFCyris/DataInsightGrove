"""attribution_position_based — U-shaped (first/last weighted)."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class AttributionPositionBasedStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; c = params["channelColumn"]
        t = params["timestampColumn"]; conv = params["convertedColumn"]
        first_w = float(params.get("firstWeight", 0.4))
        last_w = float(params.get("lastWeight", 0.4))
        middle_w = max(0.0, 1.0 - first_w - last_w)

        converters = df.filter(pl.col(conv).cast(pl.Boolean))[u].unique().to_list()
        sub = df.filter(pl.col(u).is_in(converters)).sort([u, t])

        credit: dict[str, float] = defaultdict(float)
        for (user_id,), grp in sub.group_by(u, maintain_order=True):
            channels = grp[c].to_list()
            n = len(channels)
            if n == 1:
                credit[channels[0]] += 1.0
            elif n == 2:
                credit[channels[0]] += first_w + (middle_w / 2)
                credit[channels[1]] += last_w + (middle_w / 2)
            else:
                credit[channels[0]] += first_w
                credit[channels[-1]] += last_w
                per_middle = middle_w / (n - 2)
                for ch in channels[1:-1]:
                    credit[ch] += per_middle

        out = pl.DataFrame({
            "channel": list(credit.keys()),
            "credited_conversions": list(credit.values()),
        }).sort("credited_conversions", descending=True)
        return PolarsResult(output=out)


step = AttributionPositionBasedStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

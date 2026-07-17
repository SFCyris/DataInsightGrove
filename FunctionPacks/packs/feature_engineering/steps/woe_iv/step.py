"""woe_iv — Weight of Evidence + Information Value."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class WoeIvStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cat = params["categoryColumn"]; target = params["targetColumn"]
        out_col = params.get("outputColumn") or "woe"
        # Coerce target to 0/1.
        clean = df.drop_nulls(subset=[cat, target])
        y = [int(bool(v)) for v in clean[target].to_list()]
        clean = clean.with_columns(pl.Series("__y", y))
        total_pos = max(1, sum(y))
        total_neg = max(1, len(y) - total_pos)
        agg = clean.group_by(cat).agg([
            pl.col("__y").sum().alias("__pos"),
            (pl.col("__y").count() - pl.col("__y").sum()).alias("__neg"),
        ])
        # WoE = ln((pos/total_pos) / (neg/total_neg)) per category.
        rows = agg.to_dicts()
        woe_map: dict = {}
        iv = 0.0
        for r in rows:
            p = max(1, r["__pos"]) / total_pos
            n = max(1, r["__neg"]) / total_neg
            w = math.log(p / n)
            woe_map[r[cat]] = w
            iv += (p - n) * w
        woe_col_values = [woe_map.get(v, 0.0) for v in df[cat].to_list()]
        out = df.with_columns(pl.Series(out_col, woe_col_values))
        return PolarsResult(output=out, artifacts=[{
            "kind": "metrics", "label": f"WoE / IV — {cat}",
            "data": {"information_value": round(iv, 4),
                     "interpretation": (
                         "weak" if iv < 0.1 else
                         "medium" if iv < 0.3 else
                         "strong" if iv < 0.5 else "very strong"
                     ),
                     "woe_per_category": {str(k): round(v, 4) for k, v in woe_map.items()}},
        }])


step = WoeIvStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

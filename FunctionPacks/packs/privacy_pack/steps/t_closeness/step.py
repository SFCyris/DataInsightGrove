"""t_closeness — per-class sensitive distribution within T of global."""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


def _variation_distance(p: dict, q: dict) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0) - q.get(k, 0)) for k in keys)


class TClosenessStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        qis = params.get("quasiIdentifiers") or []
        sensitive = params["sensitiveColumn"]
        t = float(params.get("t", 0.2))
        # Global distribution.
        total = df.height
        global_counts = Counter(df[sensitive].to_list())
        global_dist = {k: v / total for k, v in global_counts.items()}
        rows = []
        for class_vals, sub in df.group_by(qis):
            class_n = sub.height
            local_counts = Counter(sub[sensitive].to_list())
            local_dist = {k: v / class_n for k, v in local_counts.items()}
            d = _variation_distance(local_dist, global_dist)
            rows.append({
                **{c: v for c, v in zip(qis, class_vals)},
                "class_size": class_n, "variation_distance": d,
            })
        out = pl.DataFrame(rows).sort("variation_distance", descending=True)
        violators = out.filter(pl.col("variation_distance") > t)
        return PolarsResult(output=out, artifacts=[{
            "kind": "metrics", "label": f"T-closeness check (T={t})",
            "data": {
                "max_distance": float(out["variation_distance"].max() or 0),
                "violating_classes": int(violators.height),
                "passes_t_closeness": bool(violators.height == 0),
            },
        }])


step = TClosenessStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

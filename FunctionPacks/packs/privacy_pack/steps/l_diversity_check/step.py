"""l_diversity_check — distinct-sensitive-values per class."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class LDiversityCheckStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        qis = params.get("quasiIdentifiers") or []
        sensitive = params["sensitiveColumn"]
        l = int(params.get("l", 3))
        groups = df.group_by(qis).agg(pl.col(sensitive).n_unique().alias("distinct_sensitive"))
        violators = groups.filter(pl.col("distinct_sensitive") < l)
        return PolarsResult(output=groups.sort("distinct_sensitive"), artifacts=[{
            "kind": "metrics", "label": f"L-diversity check (L={l})",
            "data": {
                "n_classes": int(groups.height),
                "min_distinct": int(groups["distinct_sensitive"].min() or 0),
                "violating_classes": int(violators.height),
                "passes_l_diversity": bool(violators.height == 0),
            },
        }])


step = LDiversityCheckStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

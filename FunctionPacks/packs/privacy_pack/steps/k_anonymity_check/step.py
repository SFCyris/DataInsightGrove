"""k_anonymity_check — verify equivalence-class size ≥ K."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class KAnonymityCheckStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        qis = params.get("quasiIdentifiers") or []
        k = int(params.get("k", 5))
        if not qis:
            raise ValueError("k_anonymity_check: quasiIdentifiers required")
        groups = df.group_by(qis).len().rename({"len": "class_size"})
        violators = groups.filter(pl.col("class_size") < k)
        out = groups.sort("class_size").head(100)
        artifact = {
            "kind": "metrics", "label": f"K-anonymity check (K={k})",
            "data": {
                "n_classes": groups.height,
                "min_class_size": int(groups["class_size"].min() or 0),
                "max_class_size": int(groups["class_size"].max() or 0),
                "violating_classes": int(violators.height),
                "violating_rows": int(violators["class_size"].sum() or 0),
                "passes_k_anonymity": bool(violators.height == 0),
            },
        }
        return PolarsResult(output=out, artifacts=[artifact])


step = KAnonymityCheckStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""polynomial_features — degrees 2-4 + optional interactions."""
from __future__ import annotations
import json
import itertools
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class PolynomialFeaturesStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        degree = int(params.get("degree", 2))
        interactions = bool(params.get("includeInteractions", True))
        new = []
        # Powers of each column.
        for c in cols:
            for d in range(2, degree + 1):
                new.append((pl.col(c) ** d).alias(f"{c}_pow{d}"))
        # Pairwise interactions.
        if interactions and len(cols) >= 2:
            for c1, c2 in itertools.combinations(cols, 2):
                new.append((pl.col(c1) * pl.col(c2)).alias(f"{c1}_x_{c2}"))
        out = df.with_columns(new) if new else df
        return PolarsResult(output=out)


step = PolynomialFeaturesStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

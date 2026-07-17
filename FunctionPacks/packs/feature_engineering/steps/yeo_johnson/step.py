"""yeo_johnson — power transform via sklearn PowerTransformer."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class YeoJohnsonStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from sklearn.preprocessing import PowerTransformer
        df = inputs["in"]
        cols = params.get("columns") or []
        suffix = params.get("suffix") or "_yj"
        valid_cols = [c for c in cols if c in df.columns]
        if not valid_cols:
            return PolarsResult(output=df)
        sub = df.select(valid_cols).to_pandas().astype(float)
        pt = PowerTransformer(method="yeo-johnson")
        transformed = pt.fit_transform(sub.values)
        new = [pl.Series(f"{c}{suffix}", transformed[:, i].tolist())
                for i, c in enumerate(valid_cols)]
        return PolarsResult(output=df.with_columns(new))


step = YeoJohnsonStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

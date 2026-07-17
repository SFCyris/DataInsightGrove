"""impute_knn — multivariate KNN imputation via scikit-learn."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ImputeKnnStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from sklearn.impute import KNNImputer
        import numpy as np
        df = inputs["in"]
        cols = params.get("columns") or []
        k = int(params.get("k", 5))
        if len(cols) < 2:
            raise ValueError("impute_knn: need at least 2 columns for KNN imputation")
        # Subset and validate.
        sub = df.select(cols).to_pandas().astype(float)
        imputer = KNNImputer(n_neighbors=k)
        imputed = imputer.fit_transform(sub.values)
        out = df.with_columns([
            pl.Series(c, imputed[:, i].tolist()) for i, c in enumerate(cols)
        ])
        return PolarsResult(output=out)


step = ImputeKnnStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

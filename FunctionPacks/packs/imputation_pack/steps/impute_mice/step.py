"""impute_mice — multiple imputation via chained equations (sklearn IterativeImputer)."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ImputeMiceStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        # IterativeImputer is "experimental" in sklearn — explicit enable.
        from sklearn.experimental import enable_iterative_imputer  # noqa: F401
        from sklearn.impute import IterativeImputer
        df = inputs["in"]
        cols = params.get("columns") or []
        max_iter = int(params.get("maxIter", 10))
        if len(cols) < 2:
            raise ValueError("impute_mice: need at least 2 columns")
        sub = df.select(cols).to_pandas().astype(float)
        imp = IterativeImputer(max_iter=max_iter, random_state=42)
        imputed = imp.fit_transform(sub.values)
        out = df.with_columns([
            pl.Series(c, imputed[:, i].tolist()) for i, c in enumerate(cols)
        ])
        return PolarsResult(output=out)


step = ImputeMiceStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class OutliersIsolationForestStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.ensemble import IsolationForest
        import numpy as np

        df = inputs["in"]
        cols = params["columns"]
        contamination = float(params.get("contamination", 0.05))
        n_estimators = int(params.get("n_estimators", 100))
        seed = int(params.get("seed", 42))
        out_col = params.get("output_column", "is_outlier")

        if not isinstance(cols, list) or len(cols) < 2:
            raise ValueError("outliers_isolation_forest: need at least 2 columns")
        for c in cols:
            if c not in df.columns:
                raise ValueError(f"outliers_isolation_forest: column {c!r} not in input")

        # IsolationForest doesn't tolerate NaN — fill nulls with column means
        # (the alternative is dropping rows, but we want to keep the row count
        # stable so the flag column aligns with the input).
        X = df.select(cols).to_pandas()
        means = X.mean(numeric_only=True)
        X_filled = X.fillna(means)

        clf = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=seed,
            n_jobs=-1,
        )
        # IsolationForest returns -1 for anomaly, 1 for inlier
        labels = clf.fit_predict(X_filled)
        is_outlier = labels == -1

        return PolarsResult(output=df.with_columns(pl.Series(name=out_col, values=is_outlier.tolist())))


step = OutliersIsolationForestStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

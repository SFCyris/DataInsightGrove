from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _resolve_task(target: pl.Series, task: str) -> str:
    if task != "auto":
        return task
    distinct = target.n_unique()
    is_numeric = "Int" in str(target.dtype) or "Float" in str(target.dtype)
    return "regression" if is_numeric and distinct > 20 else "classification"


class PartialDependenceStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
        from sklearn.inspection import partial_dependence

        df = inputs["in"]
        target = params["target"]
        feature_cols = params["features"]
        explain = params["explain_feature"]
        task_param = params.get("task", "auto")
        grid = int(params.get("grid_resolution", 30))
        seed = int(params.get("seed", 42))

        if explain not in feature_cols:
            raise ValueError(f"partial_dependence: explain_feature {explain!r} must be in features")

        clean = df.select([target, *feature_cols]).drop_nulls()
        if clean.height < 20:
            raise ValueError("partial_dependence: need ≥20 non-null rows")

        task = _resolve_task(clean[target], task_param)
        X = clean.select(feature_cols).to_pandas()
        for c in X.columns:
            if X[c].dtype == object:
                X[c] = X[c].astype("category").cat.codes
        y = clean[target].to_pandas()
        if task == "classification" and y.dtype == object:
            y = y.astype("category").cat.codes

        if task == "regression":
            model = GradientBoostingRegressor(random_state=seed, n_estimators=80)
        else:
            model = GradientBoostingClassifier(random_state=seed, n_estimators=80)
        model.fit(X, y)
        pdp = partial_dependence(
            model, X, [feature_cols.index(explain)], grid_resolution=grid, kind="average",
        )
        # pdp.average is shape (n_classes, n_grid) for classifier, (1, n_grid) for regressor
        average = pdp["average"][0]
        values = pdp["grid_values"][0]
        rows = [
            {"feature_value": float(v), "predicted": float(a)}
            for v, a in zip(values, average)
        ]
        return PolarsResult(output=pl.DataFrame(rows))


step = PartialDependenceStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

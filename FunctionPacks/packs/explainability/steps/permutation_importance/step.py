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


class PermutationImportanceStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
        from sklearn.inspection import permutation_importance

        df = inputs["in"]
        target = params["target"]
        feature_cols = params["features"]
        task_param = params.get("task", "auto")
        n_repeats = int(params.get("n_repeats", 10))
        seed = int(params.get("seed", 42))

        if not isinstance(feature_cols, list) or not feature_cols:
            raise ValueError("permutation_importance: at least one feature required")

        clean = df.select([target, *feature_cols]).drop_nulls()
        if clean.height < 20:
            raise ValueError("permutation_importance: need ≥20 non-null rows")

        task = _resolve_task(clean[target], task_param)
        X = clean.select(feature_cols).to_pandas()
        # Quick numeric coercion — sklearn doesn't do strings.
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
        result = permutation_importance(
            model, X, y, n_repeats=n_repeats, random_state=seed, n_jobs=-1,
        )
        rows = [
            {
                "feature": col,
                "importance_mean": float(result.importances_mean[i]),
                "importance_std": float(result.importances_std[i]),
            }
            for i, col in enumerate(feature_cols)
        ]
        out_df = pl.DataFrame(rows).sort("importance_mean", descending=True)
        out_df = out_df.with_row_index(name="rank", offset=1)
        return PolarsResult(output=out_df.select(["rank", "feature", "importance_mean", "importance_std"]))


step = PermutationImportanceStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

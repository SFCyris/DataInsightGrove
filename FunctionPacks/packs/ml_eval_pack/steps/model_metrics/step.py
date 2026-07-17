from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


_NUMERIC = {"Int64", "Int32", "Int16", "Int8", "Float64", "Float32"}


def _is_numeric(dtype: pl.DataType) -> bool:
    return str(dtype) in _NUMERIC or "Int" in str(dtype) or "Float" in str(dtype)


class ModelMetricsStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn import metrics as M
        import numpy as np

        df = inputs["in"]
        actual_col = params["actual"]
        pred_col = params["predicted"]
        task = params.get("task", "auto")
        prob_col = params.get("probability_column")

        clean = df.select([c for c in (actual_col, pred_col, prob_col) if c]).drop_nulls()
        if clean.height == 0:
            raise ValueError("model_metrics: no non-null rows after filtering")

        y_true = clean[actual_col].to_numpy()
        y_pred = clean[pred_col].to_numpy()

        if task == "auto":
            actual_is_numeric = _is_numeric(df.schema[actual_col])
            distinct = clean[actual_col].n_unique()
            task = "regression" if actual_is_numeric and distinct > 20 else "classification"

        rows: list[dict[str, Any]] = []
        if task == "regression":
            rmse = float(np.sqrt(M.mean_squared_error(y_true, y_pred)))
            rows.append({
                "task": "regression",
                "n": int(len(y_true)),
                "rmse": rmse,
                "mae": float(M.mean_absolute_error(y_true, y_pred)),
                "r2": float(M.r2_score(y_true, y_pred)),
                "mean_actual": float(y_true.mean()),
                "mean_predicted": float(y_pred.mean()),
            })
        else:
            row: dict[str, Any] = {
                "task": "classification",
                "n": int(len(y_true)),
                "accuracy": float(M.accuracy_score(y_true, y_pred)),
                "precision_macro": float(M.precision_score(y_true, y_pred, average="macro", zero_division=0)),
                "recall_macro": float(M.recall_score(y_true, y_pred, average="macro", zero_division=0)),
                "f1_macro": float(M.f1_score(y_true, y_pred, average="macro", zero_division=0)),
                "n_classes": int(len(np.unique(np.concatenate([y_true, y_pred])))),
            }
            if prob_col:
                y_prob = clean[prob_col].to_numpy()
                try:
                    row["roc_auc"] = float(M.roc_auc_score(y_true, y_prob))
                    row["log_loss"] = float(M.log_loss(y_true, np.clip(y_prob, 1e-15, 1 - 1e-15)))
                except (ValueError, TypeError):
                    pass
            rows.append(row)
        return PolarsResult(output=pl.DataFrame(rows))


step = ModelMetricsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

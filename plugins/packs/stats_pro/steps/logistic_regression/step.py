"""logistic_regression — binary classification fit + predict.

Fits scikit-learn's LogisticRegression on the rows in the input frame,
then attaches per-row predicted_class + predicted_proba columns. The
fitted coefficients (one per feature plus intercept), regularization
setting, and training accuracy are emitted as a side-effect artifact
the run-detail page renders alongside the data preview.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class LogisticRegressionStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.linear_model import LogisticRegression

        df = inputs["in"]
        target = params["targetColumn"]
        features = params.get("featureColumns") or []
        if target not in df.columns:
            raise ValueError(
                f"logistic_regression: target column {target!r} not found",
            )
        if not features:
            raise ValueError(
                "logistic_regression: at least one featureColumn required",
            )
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise ValueError(
                f"logistic_regression: feature columns not found: {missing}",
            )

        regularization = (params.get("regularization") or "l2").lower()
        c = float(params.get("c") or 1.0)
        cls_name = params.get("predictedClassColumn") or "predicted_class"
        prob_name = params.get("predictedProbaColumn") or "predicted_proba"

        # Build the X matrix and y vector. Drop rows with NULL in target
        # or any feature — sklearn doesn't accept NaN by default and
        # silent imputation would hide a real data-quality issue.
        clean = df.drop_nulls(subset=[target, *features])
        if clean.height < 2:
            raise ValueError(
                "logistic_regression: fewer than 2 complete rows after "
                "dropping nulls — not enough to fit.",
            )

        X = clean.select(features).to_numpy().astype(float)
        y_raw = clean[target].to_list()
        # Accept booleans, 0/1 ints, or text "true"/"false"; coerce.
        def _coerce(v: Any) -> int:
            if isinstance(v, bool):
                return 1 if v else 0
            if isinstance(v, (int, float)):
                return int(v)
            s = str(v).strip().lower()
            if s in ("1", "true", "yes", "y", "t"):
                return 1
            if s in ("0", "false", "no", "n", "f"):
                return 0
            raise ValueError(
                f"logistic_regression: target value {v!r} is not binary",
            )
        y = np.array([_coerce(v) for v in y_raw], dtype=int)

        if set(y.tolist()) - {0, 1}:
            raise ValueError(
                "logistic_regression: target must be binary (0/1 or "
                "true/false). Convert multi-class targets via filter_rows "
                "or map them to 0/1 first.",
            )

        # sklearn parameter mapping: penalty=None disables both l1+l2.
        if regularization == "none":
            model = LogisticRegression(penalty=None, max_iter=200)
        elif regularization == "l1":
            # l1 needs the saga or liblinear solver.
            model = LogisticRegression(penalty="l1", C=c, solver="saga", max_iter=500)
        else:
            model = LogisticRegression(penalty="l2", C=c, max_iter=200)

        model.fit(X, y)
        # Now predict on the FULL input (rows with nulls in features
        # get a NULL prediction).
        predict_X = df.select(features).to_numpy().astype(float)
        any_null = np.isnan(predict_X).any(axis=1)
        proba = np.full(df.height, np.nan)
        cls = np.full(df.height, np.nan)
        valid = ~any_null
        if valid.any():
            proba[valid] = model.predict_proba(predict_X[valid])[:, 1]
            cls[valid] = model.predict(predict_X[valid]).astype(float)

        out_df = df.with_columns([
            pl.Series(cls_name, [None if np.isnan(v) else int(v) for v in cls]),
            pl.Series(prob_name, [None if np.isnan(v) else float(v) for v in proba]),
        ])

        # Side-effect artifact: coefficients + intercept + train accuracy.
        accuracy = float(model.score(X, y))
        coef_rows = [
            {"feature": f, "coefficient": float(v)}
            for f, v in zip(features, model.coef_.flatten().tolist())
        ]
        coef_rows.append({"feature": "(intercept)", "coefficient": float(model.intercept_[0])})

        artifacts: list[dict[str, Any]] = [
            {
                "kind": "metrics",
                "label": "Logistic regression fit",
                "data": {
                    "regularization": regularization,
                    "C": c if regularization != "none" else None,
                    "train_rows": int(clean.height),
                    "train_accuracy": accuracy,
                    "coefficients": coef_rows,
                    "n_features": len(features),
                },
            }
        ]
        return PolarsResult(output=out_df, artifacts=artifacts)


step = LogisticRegressionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class RocCurveStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn import metrics as M
        import numpy as np

        df = inputs["in"]
        a_col = params["actual"]
        p_col = params["probability"]
        pos = params.get("positive_label", "1")

        clean = df.select([a_col, p_col]).drop_nulls()
        if clean.height < 2:
            raise ValueError("roc_curve: need at least 2 non-null rows")

        # Coerce actual column to 0/1 against the chosen positive label
        actual_series = clean[a_col]
        # Try numeric comparison first; fall back to string equality.
        try:
            pos_value = type(actual_series[0])(pos) if actual_series[0] is not None else pos
            y_true = (actual_series == pos_value).cast(pl.Int8).to_numpy()
        except (ValueError, TypeError):
            y_true = (actual_series.cast(pl.Utf8) == str(pos)).cast(pl.Int8).to_numpy()

        if y_true.sum() == 0 or y_true.sum() == len(y_true):
            raise ValueError(
                f"roc_curve: positive_label {pos!r} matches "
                f"{int(y_true.sum())}/{len(y_true)} rows — need both classes",
            )

        y_score = clean[p_col].to_numpy()
        fpr, tpr, thresholds = M.roc_curve(y_true, y_score)
        auc = float(M.auc(fpr, tpr))

        # Replace inf threshold (sklearn convention for the very first point)
        thresholds = np.where(np.isinf(thresholds), 1.01, thresholds)

        out = pl.DataFrame({
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "threshold": thresholds.tolist(),
            "auc": [auc] * len(fpr),
        })
        return PolarsResult(output=out)


step = RocCurveStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

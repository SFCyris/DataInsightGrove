from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class TrainTestSplitStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.model_selection import train_test_split as sk_split
        import numpy as np

        df = inputs["in"]
        test_size = float(params.get("test_size", 0.2))
        stratify_col = params.get("stratify_by")
        seed = int(params.get("seed", 42))
        output_col = params.get("output_column", "split")

        n = df.height
        idx = np.arange(n)
        stratify = df[stratify_col].to_numpy() if stratify_col else None
        try:
            train_idx, test_idx = sk_split(
                idx, test_size=test_size, random_state=seed, stratify=stratify,
            )
        except ValueError as e:
            raise ValueError(f"train_test_split: {e}") from e

        labels = np.full(n, "train", dtype=object)
        labels[test_idx] = "test"
        return PolarsResult(output=df.with_columns(pl.Series(name=output_col, values=labels.tolist())))


step = TrainTestSplitStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

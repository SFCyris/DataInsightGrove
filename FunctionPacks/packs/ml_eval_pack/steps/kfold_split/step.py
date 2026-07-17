from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class KFoldSplitStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.model_selection import KFold, StratifiedKFold
        import numpy as np

        df = inputs["in"]
        n_splits = int(params.get("n_splits", 5))
        stratify_col = params.get("stratify_by")
        seed = int(params.get("seed", 42))
        output_col = params.get("output_column", "fold")

        n = df.height
        if n_splits > n:
            raise ValueError(f"kfold_split: n_splits ({n_splits}) > n_rows ({n})")

        idx = np.arange(n)
        labels = np.zeros(n, dtype=int)
        if stratify_col:
            y = df[stratify_col].to_numpy()
            kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
            iterator = kf.split(idx, y)
        else:
            kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
            iterator = kf.split(idx)

        for fold_id, (_, test_idx) in enumerate(iterator):
            labels[test_idx] = fold_id

        return PolarsResult(output=df.with_columns(pl.Series(name=output_col, values=labels.tolist())))


step = KFoldSplitStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

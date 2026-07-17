"""undersample — random undersampling of majority class."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class UndersampleStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        target = params["targetColumn"]
        ratio = float(params.get("ratio", 1.0))
        seed = int(params.get("seed", 42))
        cnt = Counter(df[target].to_list())
        if len(cnt) < 2:
            return PolarsResult(output=df)
        min_class_count = min(cnt.values())
        target_majority_count = int(min_class_count * ratio)
        rng = np.random.default_rng(seed)
        chunks = []
        for cls, count in cnt.items():
            sub = df.filter(pl.col(target) == cls)
            if count > target_majority_count:
                chunks.append(sub.sample(n=target_majority_count, seed=seed))
            else:
                chunks.append(sub)
        return PolarsResult(output=pl.concat(chunks))


step = UndersampleStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""smote_oversample — synthetic minority oversampling via imblearn."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SmoteOversampleStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from imblearn.over_sampling import SMOTE
        df = inputs["in"]
        target = params["targetColumn"]
        features = params.get("featureColumns") or []
        k = int(params.get("k", 5))
        seed = int(params.get("seed", 42))
        if not features:
            raise ValueError("smote_oversample: featureColumns required")
        clean = df.drop_nulls(subset=[target, *features])
        X = clean.select(features).to_numpy().astype(float)
        y = clean[target].to_list()
        # k_neighbors must be < smallest class size; clamp.
        from collections import Counter
        cnt = Counter(y); min_class = min(cnt.values())
        k_eff = min(k, max(1, min_class - 1))
        smote = SMOTE(k_neighbors=k_eff, random_state=seed)
        X_res, y_res = smote.fit_resample(X, y)
        out_cols = {c: X_res[:, i].tolist() for i, c in enumerate(features)}
        out_cols[target] = y_res.tolist() if hasattr(y_res, "tolist") else list(y_res)
        return PolarsResult(output=pl.DataFrame(out_cols))


step = SmoteOversampleStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

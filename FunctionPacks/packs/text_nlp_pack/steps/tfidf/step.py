"""tfidf — top-K TF-IDF terms per document."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class TfidfStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from sklearn.feature_extraction.text import TfidfVectorizer
        df = inputs["in"]
        col = params["textColumn"]
        top_k = int(params.get("topK", 5))
        max_feat = int(params.get("maxFeatures", 1000))
        texts = [str(t or "") for t in df[col].to_list()]
        vec = TfidfVectorizer(max_features=max_feat, stop_words="english")
        mat = vec.fit_transform(texts)
        vocab = vec.get_feature_names_out()
        top_terms = []
        for i in range(mat.shape[0]):
            row = mat.getrow(i).toarray().flatten()
            idx = np.argsort(-row)[:top_k]
            top_terms.append([vocab[j] for j in idx if row[j] > 0])
        out = df.with_columns(pl.Series("top_tfidf_terms", top_terms))
        return PolarsResult(output=out)


step = TfidfStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

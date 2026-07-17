"""lda_topics — sklearn LatentDirichletAllocation."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class LdaTopicsStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from sklearn.feature_extraction.text import CountVectorizer
        from sklearn.decomposition import LatentDirichletAllocation
        df = inputs["in"]
        col = params["textColumn"]
        n_topics = int(params.get("nTopics", 5))
        seed = int(params.get("seed", 42))
        texts = [str(t or "") for t in df[col].to_list()]
        vec = CountVectorizer(stop_words="english", max_features=2000)
        X = vec.fit_transform(texts)
        lda = LatentDirichletAllocation(n_components=n_topics, random_state=seed).fit(X)
        # Per doc: argmax topic.
        doc_topics = lda.transform(X).argmax(axis=1).tolist()
        # Top terms per topic.
        vocab = vec.get_feature_names_out()
        top_terms_per_topic = []
        for k in range(n_topics):
            top_idx = np.argsort(-lda.components_[k])[:10]
            top_terms_per_topic.append([vocab[i] for i in top_idx])
        out = df.with_columns([
            pl.Series("dominant_topic", doc_topics),
            pl.Series("topic_top_terms",
                       [top_terms_per_topic[t] for t in doc_topics]),
        ])
        return PolarsResult(output=out, artifacts=[{
            "kind": "metrics", "label": f"LDA topics ({n_topics})",
            "data": {"top_terms_per_topic": {f"topic_{k}": top_terms_per_topic[k] for k in range(n_topics)}},
        }])


step = LdaTopicsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

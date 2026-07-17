"""bertopic_topics — transformer-based topic modelling."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class BertopicTopicsStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        try:
            from bertopic import BERTopic
        except ImportError as e:
            raise ImportError(
                "bertopic_topics requires bertopic + sentence-transformers + "
                "umap-learn + hdbscan. See FunctionPacks/packs/text_nlp_pack/"
                "INTERNAL_NOTES.md for install + sizing guidance."
            ) from e
        df = inputs["in"]
        col = params["textColumn"]
        min_size = int(params.get("minTopicSize", 10))
        texts = [str(t or "") for t in df[col].to_list()]
        model = BERTopic(min_topic_size=min_size, verbose=False)
        topics, _ = model.fit_transform(texts)
        info = model.get_topic_info()
        out = df.with_columns(pl.Series("bertopic_topic", topics))
        return PolarsResult(output=out, artifacts=[{
            "kind": "metrics", "label": "BERTopic summary",
            "data": {"n_topics": len(set(topics)),
                      "topic_info": info.head(15).to_dict(orient="records")},
        }])


step = BertopicTopicsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

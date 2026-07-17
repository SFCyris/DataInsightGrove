"""sentiment_vader — VADER sentiment per row."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SentimentVaderStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        except ImportError as e:
            raise ImportError(
                "sentiment_vader requires vaderSentiment. Install via "
                "`pip install vaderSentiment`. See INTERNAL_NOTES.md."
            ) from e
        df = inputs["in"]
        col = params["textColumn"]
        sia = SentimentIntensityAnalyzer()
        compound, pos, neg, neu = [], [], [], []
        for t in df[col].to_list():
            scores = sia.polarity_scores(str(t or ""))
            compound.append(float(scores["compound"]))
            pos.append(float(scores["pos"]))
            neg.append(float(scores["neg"]))
            neu.append(float(scores["neu"]))
        out = df.with_columns([
            pl.Series("sentiment_compound", compound),
            pl.Series("sentiment_positive", pos),
            pl.Series("sentiment_negative", neg),
            pl.Series("sentiment_neutral", neu),
        ])
        return PolarsResult(output=out)


step = SentimentVaderStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

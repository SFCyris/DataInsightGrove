"""tokenize — word / sentence / n-gram tokenisation."""
from __future__ import annotations
import json
import re
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


_WORD_RE = re.compile(r"\b\w+\b")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


class TokenizeStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        col = params["textColumn"]
        mode = (params.get("mode") or "word").lower()
        ngram_size = int(params.get("ngramSize", 2))
        lowercase = bool(params.get("lowercase", True))
        out_col = params.get("outputColumn") or "tokens"

        def _tokens(s):
            if s is None: return []
            text = str(s)
            if lowercase: text = text.lower()
            if mode == "sentence":
                return [seg.strip() for seg in _SENT_RE.split(text) if seg.strip()]
            words = _WORD_RE.findall(text)
            if mode == "ngram":
                return [" ".join(words[i:i + ngram_size])
                        for i in range(len(words) - ngram_size + 1)]
            return words

        out = df.with_columns(
            pl.Series(out_col, [_tokens(v) for v in df[col].to_list()])
        )
        return PolarsResult(output=out)


step = TokenizeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

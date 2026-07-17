"""pii_redact — regex-replace common PII patterns."""
from __future__ import annotations
import json
import re
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


_PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn":   re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
}


class PiiRedactStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        active = [_PATTERNS[p.strip()] for p in (params.get("patterns") or "email").split(",")
                   if p.strip() in _PATTERNS]
        replacement = params.get("replacement") or "[REDACTED]"

        def _redact(s):
            if s is None: return None
            text = str(s)
            for pat in active:
                text = pat.sub(replacement, text)
            return text

        for c in cols:
            if c not in df.columns: continue
            df = df.with_columns(pl.Series(c, [_redact(v) for v in df[c].to_list()]))
        return PolarsResult(output=df)


step = PiiRedactStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

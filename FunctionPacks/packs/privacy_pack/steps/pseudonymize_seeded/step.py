"""pseudonymize_seeded — HMAC-SHA256 deterministic tokenization."""
from __future__ import annotations
import hashlib
import hmac
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class PseudonymizeSeededStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        seed = params["seed"].encode("utf-8")
        prefix = params.get("prefix") or "px_"
        for c in cols:
            if c not in df.columns: continue
            tokens = [
                prefix + hmac.new(seed, str(v).encode("utf-8"), hashlib.sha256).hexdigest()[:16]
                if v is not None else None
                for v in df[c].to_list()
            ]
            df = df.with_columns(pl.Series(c, tokens))
        return PolarsResult(output=df)


step = PseudonymizeSeededStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

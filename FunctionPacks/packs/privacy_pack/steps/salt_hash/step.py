"""salt_hash — salted SHA256 hash of values."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SaltHashStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        salt = params["salt"].encode("utf-8")
        n = int(params.get("truncate", 16))
        for c in cols:
            if c not in df.columns: continue
            hashed = [
                hashlib.sha256(salt + str(v).encode("utf-8")).hexdigest()[:n]
                if v is not None else None
                for v in df[c].to_list()
            ]
            df = df.with_columns(pl.Series(c, hashed))
        return PolarsResult(output=df)


step = SaltHashStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

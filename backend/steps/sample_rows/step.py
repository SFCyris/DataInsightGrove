from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step


class SampleRowsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        kind = params.get("kind") or "head"
        if kind == "head":
            n = int(params.get("n") or 1000)
            return f"SELECT * FROM {src} LIMIT {n}"
        if kind == "tail":
            n = int(params.get("n2") or 1000)
            # Tail = OFFSET total-n; cheaper without count: use a CTE.
            return (
                f"WITH __t AS (SELECT *, row_number() OVER () AS __rn, count(*) OVER () AS __c FROM {src}) "
                f"SELECT * EXCLUDE (__rn, __c) FROM __t WHERE __rn > __c - {n}"
            )
        if kind == "random_n":
            n = int(params.get("n3") or 1000)
            seed = int(params.get("seed") or 42)
            # USING SAMPLE n ROWS gives reproducible random sample with seed.
            return f"SELECT * FROM {src} USING SAMPLE {n} ROWS (reservoir, {seed})"
        if kind == "random_pct":
            pct = float(params.get("pct") or 10)
            return f"SELECT * FROM {src} USING SAMPLE {pct} PERCENT (bernoulli)"
        return f"SELECT * FROM {src}"


step = SampleRowsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

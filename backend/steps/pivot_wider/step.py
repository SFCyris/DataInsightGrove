from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident

_AGG_TO_SQL = {"sum": "SUM", "mean": "AVG", "min": "MIN", "max": "MAX", "first": "FIRST"}


class PivotWiderStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        ids = params.get("id") or []
        names = params["names"]
        values = params["values"]
        agg = _AGG_TO_SQL.get(params.get("agg") or "sum", "SUM")

        id_cols = ", ".join(quote_ident(c) for c in ids)
        # DuckDB's PIVOT statement.
        return (
            f"PIVOT {src} ON {quote_ident(names)} "
            f"USING {agg}({quote_ident(values)})"
            + (f" GROUP BY {id_cols}" if id_cols else "")
        )

    def infer_schema(self, input_schemas, params):
        # Output schema isn't fully knowable until execution because the new
        # column names depend on data values. Best effort: include id columns + 'unknown' star.
        in_schema = input_schemas.get("in", {})
        out: dict[str, str] = {}
        for c in params.get("id") or []:
            out[c] = in_schema.get(c, "unknown")
        return out


step = PivotWiderStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

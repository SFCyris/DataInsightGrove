from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str

_PART_TO_FN = {
    "year": "year", "quarter": "quarter", "month": "month", "week": "week",
    "day": "day", "dayofweek": "isodow", "hour": "hour", "minute": "minute", "second": "second",
}


class ExtractDatePartsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        parts = params.get("parts") or []
        prefix = params.get("prefix") or ""
        if not parts:
            return f"SELECT * FROM {src}"
        col_name = params["column"]
        cols: list[str] = []
        for p in parts:
            fn = _PART_TO_FN.get(p)
            if not fn:
                continue
            alias = quote_ident(f"{prefix}{col_name}_{p}" if prefix else f"{col_name}_{p}")
            cols.append(f"date_part({quote_str(fn)}, {col}) AS {alias}")
        if not cols:
            return f"SELECT * FROM {src}"
        return f"SELECT *, {', '.join(cols)} FROM {src}"

    def infer_schema(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        col_name = params.get("column", "")
        prefix = params.get("prefix") or ""
        for p in params.get("parts") or []:
            alias = f"{prefix}{col_name}_{p}" if prefix else f"{col_name}_{p}"
            s[alias] = "integer"
        return s


step = ExtractDatePartsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


class PivotLongerStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        ids = params.get("id") or []
        value_cols = params.get("value_cols") or []
        names_to = params.get("names_to") or "name"
        values_to = params.get("values_to") or "value"
        if not value_cols:
            return f"SELECT * FROM {src}"
        # DuckDB UNPIVOT: convert wide to long.
        id_list = ", ".join(quote_ident(c) for c in ids)
        value_list = ", ".join(quote_ident(c) for c in value_cols)
        # If id list empty, select only the unpivoted columns.
        select_clause = (id_list + ", " if id_list else "") + f"name AS {quote_ident(names_to)}, value AS {quote_ident(values_to)}"
        return (
            f"SELECT {select_clause} FROM ("
            f"  UNPIVOT {src} ON {value_list} INTO NAME name VALUE value"
            f")"
        )

    def infer_schema(self, input_schemas, params):
        in_schema = input_schemas.get("in", {})
        out: dict[str, str] = {}
        for c in params.get("id") or []:
            out[c] = in_schema.get(c, "unknown")
        out[params.get("names_to") or "name"] = "string"
        # Common inferred type from value cols (default unknown if mixed).
        vcols = params.get("value_cols") or []
        types = {in_schema.get(c) for c in vcols if c in in_schema}
        out[params.get("values_to") or "value"] = next(iter(types)) if len(types) == 1 else "unknown"
        return out


step = PivotLongerStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

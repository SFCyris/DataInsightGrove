from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class CoalesceColumnsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        cols = params.get("columns") or []
        if not cols:
            return f"SELECT * FROM {src}"
        alias = quote_ident(params["as"])
        coalesce = "COALESCE(" + ", ".join(quote_ident(c) for c in cols) + ")"
        if params.get("drop"):
            excludes = ", ".join(quote_ident(c) for c in cols)
            return f"SELECT * EXCLUDE ({excludes}), {coalesce} AS {alias} FROM {src}"
        return f"SELECT *, {coalesce} AS {alias} FROM {src}"

    def infer_schema(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        cols = params.get("columns") or []
        if params.get("drop"):
            for c in cols:
                s.pop(c, None)
        if params.get("as"):
            # type = first source column's type, fallback unknown
            t = next((s.get(c) for c in cols if c in input_schemas["in"]), None) or "unknown"
            # Note: if drop=true we already removed sources; recompute type from input_schemas.
            t = next(
                (input_schemas["in"].get(c) for c in cols if c in input_schemas["in"]),
                "unknown",
            ) or "unknown"
            s[params["as"]] = t
        return s


step = CoalesceColumnsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


class SplitColumnStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col_name = params["column"]
        col = quote_ident(col_name)
        delim = quote_str(params.get("delimiter") or ",")
        parts = max(1, int(params.get("parts") or 2))
        drop = bool(params.get("drop"))
        # str_split(col, delim) returns a LIST<VARCHAR>; index from 1.
        new_cols = ", ".join(
            f"str_split({col}, {delim})[{i + 1}] AS {quote_ident(col_name + '_' + str(i + 1))}"
            for i in range(parts)
        )
        if drop:
            return f"SELECT * EXCLUDE ({col}), {new_cols} FROM {src}"
        return f"SELECT *, {new_cols} FROM {src}"

    def infer_schema(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        col_name = params.get("column")
        parts = int(params.get("parts") or 2)
        drop = bool(params.get("drop"))
        if drop and col_name in s:
            s.pop(col_name)
        for i in range(parts):
            s[f"{col_name}_{i + 1}"] = "string"
        return s


step = SplitColumnStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

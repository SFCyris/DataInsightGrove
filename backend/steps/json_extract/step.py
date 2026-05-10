from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


class JsonExtractStep(Step):
    """SELECT *, json_extract(col, '$.path') AS new_col FROM src.

    DuckDB exposes both json_extract (returns JSON-typed) and
    json_extract_string (returns VARCHAR — coerces). We pick based on
    the asText param.
    """

    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        path = params.get("path") or "$"
        if not isinstance(path, str):
            raise ValueError("path must be a string")
        if not path.startswith("$"):
            raise ValueError("path must start with '$' (e.g. $.field, $.items[0].name)")
        # Reject obvious SQL-escape tries — paths are quoted as a string
        # literal, so single quotes have to be escaped, and we do that via
        # quote_str. But disallow embedded backticks that DuckDB might
        # mis-parse in some edge cases.
        if "`" in path or "\x00" in path:
            raise ValueError("path contains illegal characters")
        out = params["outputColumn"]
        if not isinstance(out, str) or not out:
            raise ValueError("outputColumn is required")
        as_text = bool(params.get("asText", False))

        fn = "json_extract_string" if as_text else "json_extract"
        expr = f"{fn}({col}, {quote_str(path)})"
        return f"SELECT *, {expr} AS {quote_ident(out)} FROM {src}"

    def infer_schema(
        self, input_schemas: dict[str, dict[str, str]], params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        out = params.get("outputColumn")
        if out:
            # asText forces string; otherwise the type is dynamic per-row,
            # so we report 'json' which the grid renders as JSON.
            s[str(out)] = "string" if params.get("asText") else "json"
        return s


step = JsonExtractStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

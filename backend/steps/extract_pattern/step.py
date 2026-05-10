from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


class ExtractPatternStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        # Validate the regex compiles before handing it to DuckDB. Pattern is
        # already a SQL string literal (quote_str); group is int-cast — no
        # SQL-injection surface, but a malformed regex would crash mid-run.
        try:
            re.compile(params["pattern"])
        except re.error as e:
            raise ValueError(f"extract_pattern: invalid regex {params['pattern']!r}: {e}") from e
        pattern = quote_str(params["pattern"])
        group = int(params.get("group") or 1)
        alias = quote_ident(params["as"])
        return f"SELECT *, regexp_extract({col}, {pattern}, {group}) AS {alias} FROM {src}"

    def infer_schema(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        if params.get("as"):
            s[params["as"]] = "string"
        return s


step = ExtractPatternStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

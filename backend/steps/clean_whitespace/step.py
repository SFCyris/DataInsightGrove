from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


class CleanWhitespaceStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        expr = f"trim({col})"
        if params.get("collapse"):
            ws = quote_str(r"\s+")
            expr = f"regexp_replace({expr}, {ws}, ' ', 'g')"
        if params.get("lowercase"):
            expr = f"lower({expr})"
        return f"SELECT * REPLACE ({expr} AS {col}) FROM {src}"


step = CleanWhitespaceStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

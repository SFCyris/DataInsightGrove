from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


class ReplaceTextStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        find = quote_str(params["find"])
        repl = quote_str(params.get("replace") or "")
        if params.get("regex"):
            expr = f"regexp_replace({col}, {find}, {repl}, 'g')"
        else:
            expr = f"replace({col}, {find}, {repl})"
        return f"SELECT * REPLACE ({expr} AS {col}) FROM {src}"


step = ReplaceTextStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, assert_safe_expr, quote_ident


class DeriveColumnStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        name = params["name"]
        expr = assert_safe_expr(params["expression"], kind="expression")
        return f"SELECT *, ({expr}) AS {quote_ident(name)} FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        name = params.get("name")
        if name:
            # We don't statically evaluate the expression; downstream column type is unknown.
            s[name] = "unknown"
        return s


step = DeriveColumnStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

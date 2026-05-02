from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class SelectColumnsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        cols = params.get("columns") or []
        if not cols:
            return f'SELECT * FROM {src}'
        cols_sql = ", ".join(quote_ident(c) for c in cols)
        return f'SELECT {cols_sql} FROM {src}'

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        in_schema = input_schemas["in"]
        cols = params.get("columns") or []
        if not cols:
            return dict(in_schema)
        return {c: in_schema[c] for c in cols if c in in_schema}


step = SelectColumnsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

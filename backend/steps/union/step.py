from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step


class UnionStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        a = inputs["top"]
        b = inputs["bottom"]
        op = "UNION" if params.get("distinct") else "UNION ALL"
        # UNION BY NAME aligns columns by column name across the two inputs.
        return f"SELECT * FROM {a} {op} BY NAME SELECT * FROM {b}"

    def infer_schema(self, input_schemas, params):
        top = input_schemas.get("top", {})
        bottom = input_schemas.get("bottom", {})
        out = dict(top)
        for k, v in bottom.items():
            out.setdefault(k, v)
        return out


step = UnionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

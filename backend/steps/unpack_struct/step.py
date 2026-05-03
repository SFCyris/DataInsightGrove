from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


def _validate_field_name(name: Any) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("field name must be a non-empty string")
    if not name.replace("_", "").isalnum():
        raise ValueError(f"field name {name!r} must be snake_case alphanumeric")
    return name


class UnpackStructStep(Step):
    """SELECT * EXCLUDE (struct_col),
              struct_col.field1 AS prefix_field1,
              struct_col.field2 AS prefix_field2 FROM src.

    EXCLUDE drops the source struct so the output schema is flat.
    """

    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = params["column"]
        if not isinstance(col, str) or not col:
            raise ValueError("column is required")
        fields = params.get("fields") or []
        if not fields:
            raise ValueError("at least one field name is required")
        prefix = params.get("outputPrefix") or ""
        if prefix and not isinstance(prefix, str):
            raise ValueError("outputPrefix must be a string")

        col_q = quote_ident(col)
        select_pieces = [f"* EXCLUDE ({col_q})"]
        for f in fields:
            fname = _validate_field_name(f)
            out_name = f"{prefix}{fname}"
            select_pieces.append(f"{col_q}.{fname} AS {quote_ident(out_name)}")
        return f"SELECT {', '.join(select_pieces)} FROM {src}"

    def infer_schema(
        self, input_schemas: dict[str, dict[str, str]], params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        col = params.get("column")
        prefix = params.get("outputPrefix") or ""
        fields = params.get("fields") or []
        if col and col in s:
            s.pop(col, None)
        for f in fields:
            if isinstance(f, str):
                s[f"{prefix}{f}"] = "double"  # struct fields default to double in our spatial types
        return s


step = UnpackStructStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

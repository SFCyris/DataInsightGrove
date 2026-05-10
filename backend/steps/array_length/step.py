from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class ArrayLengthStep(Step):
    """SELECT *, len(col) AS out_col FROM src.

    `len()` works on both LIST and ARRAY (fixed-size) columns in DuckDB.
    Returns NULL for NULL inputs, 0 for empty arrays.
    """

    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = params["column"]
        if not isinstance(col, str) or not col:
            raise ValueError("column is required")
        out = params["outputColumn"]
        if not isinstance(out, str) or not out:
            raise ValueError("outputColumn is required")
        return f"SELECT *, len({quote_ident(col)}) AS {quote_ident(out)} FROM {src}"

    def infer_schema(
        self, input_schemas: dict[str, dict[str, str]], params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        out = params.get("outputColumn")
        if out:
            s[str(out)] = "integer"
        return s


step = ArrayLengthStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

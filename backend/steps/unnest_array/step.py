from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class UnnestArrayStep(Step):
    """SELECT * EXCLUDE (col), unnest(col) AS out_col FROM src.

    With preserveNulls=true, we emit unnest(coalesce(col, [NULL])) so a
    NULL or empty array still produces one row (with NULL in the new
    column). With preserveNulls=false, NULL/empty arrays drop the row.
    """

    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = params["column"]
        if not isinstance(col, str) or not col:
            raise ValueError("column is required")
        col_q = quote_ident(col)
        out_name = params.get("outputColumn") or col
        out_q = quote_ident(out_name)
        preserve = bool(params.get("preserveNulls", True))

        if preserve:
            # Coalesce NULL → [NULL]; if the array has zero elements,
            # array_length(coalesce(...,[NULL])) = 1 so we still get a row.
            # When the array is empty (length 0), DuckDB's unnest drops
            # the row, so we additionally CASE in a [NULL] placeholder.
            unnest_expr = (
                f"unnest("
                f"  CASE WHEN {col_q} IS NULL OR len({col_q}) = 0 "
                f"  THEN [NULL] "
                f"  ELSE {col_q} "
                f"  END"
                f")"
            )
        else:
            unnest_expr = f"unnest({col_q})"

        return f"SELECT * EXCLUDE ({col_q}), {unnest_expr} AS {out_q} FROM {src}"

    def infer_schema(
        self, input_schemas: dict[str, dict[str, str]], params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        col = params.get("column")
        out_name = params.get("outputColumn") or col
        if col:
            s.pop(col, None)
        if out_name:
            # We don't know the array's element type without inspecting
            # the upstream more deeply; default to string.
            s[str(out_name)] = "string"
        return s


step = UnnestArrayStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

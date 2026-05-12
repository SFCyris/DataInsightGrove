from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, assert_safe_expr, quote_ident


def _validate_column_name(name: Any) -> str:
    """Same shape as derive_column._validate_column_name. Pen-tester
    consistency fix: the math_equation step previously accepted arbitrary
    `resultName` values straight into `quote_ident`, including NUL bytes
    + control chars + leading/trailing whitespace, which could collide with
    downstream identifier consumers. Now matches derive_column's discipline.
    """
    if not isinstance(name, str):
        raise ValueError("math_equation: `resultName` must be a string")
    s = name.strip()
    if not s:
        raise ValueError("math_equation: `resultName` cannot be empty")
    if "\x00" in s:
        raise ValueError("math_equation: `resultName` cannot contain NUL bytes")
    if any(0 <= ord(c) <= 31 for c in s):
        raise ValueError("math_equation: `resultName` cannot contain control characters")
    return s


class MathEquationStep(Step):
    def to_sql(
        self,
        params: dict[str, Any],
        inputs: dict[str, str],
        *,
        input_schemas: dict[str, dict[str, str]] | None = None,
    ) -> str:
        src = inputs["in"]
        name = _validate_column_name(params["resultName"])
        # assert_safe_expr blocks DDL/IO/multi-statement payloads. The user's
        # math expression itself can contain arbitrary column references, the
        # standard arithmetic operators, and DuckDB math functions — those
        # aren't on the deny-list.
        equation = assert_safe_expr(params["equation"], kind="equation")
        position = (params.get("position") or "end").lower()
        reference = params.get("reference")

        new_col_quoted = quote_ident(name)
        new_col_select = f"({equation}) AS {new_col_quoted}"

        if position == "start":
            return f"SELECT {new_col_select}, * FROM {src}"
        if position == "end" or position not in ("before", "after"):
            return f"SELECT *, {new_col_select} FROM {src}"

        # before/after needs schema. Same fallback semantics as add_column —
        # if we can't resolve, append at end so the user still gets the
        # computed column (no data lost, no SQL error).
        if input_schemas is None or "in" not in input_schemas or not reference:
            return f"SELECT *, {new_col_select} FROM {src}"
        in_cols = list(input_schemas["in"].keys())
        if reference not in in_cols:
            return f"SELECT *, {new_col_select} FROM {src}"

        parts: list[str] = []
        for c in in_cols:
            if position == "before" and c == reference:
                parts.append(new_col_select)
            parts.append(quote_ident(c))
            if position == "after" and c == reference:
                parts.append(new_col_select)
        return f"SELECT {', '.join(parts)} FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        in_schema = input_schemas["in"]
        name = params.get("resultName")
        if not name:
            return dict(in_schema)
        # We don't statically evaluate the expression — downstream column
        # type is unknown. Same posture as derive_column.
        position = (params.get("position") or "end").lower()
        reference = params.get("reference")
        if position == "start":
            return {name: "unknown", **in_schema}
        if position in ("before", "after") and reference and reference in in_schema:
            result: dict[str, str] = {}
            for k, v in in_schema.items():
                if position == "before" and k == reference:
                    result[name] = "unknown"
                result[k] = v
                if position == "after" and k == reference:
                    result[name] = "unknown"
            return result
        return {**in_schema, name: "unknown"}


step = MathEquationStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

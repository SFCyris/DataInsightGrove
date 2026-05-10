from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


# DIG logical type → DuckDB SQL type for the explicit CAST. Keeping the map
# tight (no aliases / synonyms) so the manifest's enum and this dict stay in
# 1:1 correspondence — adding a new logical type means updating both.
_SQL_TYPES = {
    "string": "VARCHAR",
    "integer": "BIGINT",
    "double": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
}


def _value_expr(default: str | None, sql_type: str) -> str:
    """Compose the SQL expression that fills the new column.

    Empty / missing default → typed NULL. Otherwise wrap the user's text as a
    string literal and let DuckDB cast it (handles 'true' → BOOLEAN,
    '2024-01-01' → DATE, '42' → BIGINT, etc. — same string-coercion rules
    DuckDB uses everywhere else, so the user's mental model carries over).
    """
    if default is None or default == "":
        return f"CAST(NULL AS {sql_type})"
    return f"CAST({quote_str(default)} AS {sql_type})"


class AddColumnStep(Step):
    def to_sql(
        self,
        params: dict[str, Any],
        inputs: dict[str, str],
        *,
        input_schemas: dict[str, dict[str, str]] | None = None,
    ) -> str:
        src = inputs["in"]
        name = params["name"]
        col_type = params.get("columnType", "string")
        sql_type = _SQL_TYPES.get(col_type, "VARCHAR")
        default = params.get("defaultValue")
        position = (params.get("position") or "end").lower()
        reference = params.get("reference")

        new_col_quoted = quote_ident(name)
        value_sql = _value_expr(default, sql_type)
        new_col_select = f"{value_sql} AS {new_col_quoted}"

        # Position cases that don't need schema knowledge — the common path.
        if position == "start":
            return f"SELECT {new_col_select}, * FROM {src}"
        if position == "end" or position not in ("before", "after"):
            return f"SELECT *, {new_col_select} FROM {src}"

        # before/after: need to know the input column order so we can splice
        # the new column into the right slot. The executor passes
        # `input_schemas` only for steps that opt in (this one). If for some
        # reason the schema isn't available — or the reference column is
        # missing — fall back to appending at the end, which is the safest
        # behavior (no data lost, no SQL error).
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
        name = params.get("name")
        col_type = params.get("columnType", "string")
        position = (params.get("position") or "end").lower()
        reference = params.get("reference")
        if not name:
            return dict(in_schema)

        if position == "start":
            return {name: col_type, **in_schema}
        if position in ("before", "after") and reference and reference in in_schema:
            result: dict[str, str] = {}
            for k, v in in_schema.items():
                if position == "before" and k == reference:
                    result[name] = col_type
                result[k] = v
                if position == "after" and k == reference:
                    result[name] = col_type
            return result
        # default: end (also covers reference missing / ignored)
        return {**in_schema, name: col_type}


step = AddColumnStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

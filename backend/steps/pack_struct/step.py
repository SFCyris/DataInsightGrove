from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


def _validate_field_name(name: Any) -> str:
    """Struct field names go directly into a SQL identifier — sanitize."""
    if not isinstance(name, str) or not name:
        raise ValueError("field name must be a non-empty string")
    # Allow alphanumeric + underscore. Reject anything that could escape
    # the struct_pack(..) call into surrounding SQL.
    if not name.replace("_", "").isalnum():
        raise ValueError(f"field name {name!r} must be snake_case alphanumeric")
    return name


class PackStructStep(Step):
    """SELECT *, struct_pack(field1 := col1, field2 := col2) AS new_col FROM src."""

    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        out_col = params["outputColumn"]
        if not isinstance(out_col, str) or not out_col:
            raise ValueError("outputColumn must be a non-empty string")
        fields = params.get("fields") or []
        if not fields:
            raise ValueError("at least one field is required")

        pieces: list[str] = []
        for f in fields:
            fname = _validate_field_name(f.get("fieldName"))
            scol = f.get("sourceColumn")
            if not isinstance(scol, str) or not scol:
                raise ValueError(f"field {fname!r}: sourceColumn is required")
            pieces.append(f"{fname} := {quote_ident(scol)}")

        pack_expr = f"struct_pack({', '.join(pieces)})"
        return f"SELECT *, {pack_expr} AS {quote_ident(out_col)} FROM {src}"

    def infer_schema(
        self, input_schemas: dict[str, dict[str, str]], params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        out_col = params.get("outputColumn")
        # We can't synthesize the precise STRUCT(field1 DOUBLE, field2 DOUBLE)
        # type without inspecting source-column types. The frontend's
        # logicalType() falls back to "string" for unknown types, which
        # means the new column appears in the grid with no special
        # treatment. The user typically casts it to cartesian2d / polar2d
        # / geographic immediately after, which sets the proper logical type.
        if out_col:
            s[str(out_col)] = "struct"
        return s


step = PackStructStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

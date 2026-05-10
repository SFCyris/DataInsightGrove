from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import ColumnLineage, ColumnRef, Step, quote_ident


class RenameColumnsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        mapping = params.get("mapping") or []
        if not mapping:
            return f"SELECT * FROM {src}"
        # Use DuckDB's SELECT * RENAME (a AS b, c AS d) FROM …
        renames = ", ".join(
            f"{quote_ident(m['from'])} AS {quote_ident(m['to'])}" for m in mapping
        )
        return f"SELECT * RENAME ({renames}) FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        in_schema = input_schemas["in"]
        rename = {m["from"]: m["to"] for m in (params.get("mapping") or []) if m.get("from") and m.get("to")}
        return {rename.get(k, k): v for k, v in in_schema.items()}

    def column_dependencies(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        in_cols = input_schemas["in"]
        rename = {m["from"]: m["to"] for m in (params.get("mapping") or []) if m.get("from") and m.get("to")}
        out: dict[str, ColumnLineage] = {}
        for src_col in in_cols:
            new_name = rename.get(src_col, src_col)
            transform = "passthrough" if new_name == src_col else f"renamed from `{src_col}`"
            out[new_name] = ColumnLineage(
                sources=[ColumnRef(port="in", column=src_col)],
                transform=transform,
                expression=None,
                is_passthrough=(new_name == src_col),
            )
        return out


step = RenameColumnsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

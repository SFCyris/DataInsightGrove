from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dig.engine.step import ColumnLineage, ColumnRef, Step, assert_safe_expr, quote_ident


_IDENT_RE = re.compile(r'"([^"]+)"|\b([A-Za-z_][A-Za-z0-9_]*)\b')


def _extract_column_refs(expression: str, known_columns: set[str]) -> list[str]:
    """Best-effort: pull column identifiers out of a SQL expression.

    Matches double-quoted identifiers and bare identifiers, intersected with
    the known schema. Doesn't try to be a full parser — false-positives are
    fine (we'd report spurious deps), but false-negatives degrade lineage,
    so we err on the side of recall."""
    found: list[str] = []
    for m in _IDENT_RE.finditer(expression):
        ident = m.group(1) or m.group(2)
        if ident in known_columns and ident not in found:
            found.append(ident)
    return found


def _validate_column_name(name: Any) -> str:
    """Reject empty / whitespace-only / NUL-bearing names. `assert_safe_expr`
    runs on the expression but the column name was previously trusted —
    `name=""` produced `AS ""` (invalid SQL on most dialects), and a NUL
    byte would truncate the identifier in some downstream clients."""
    if not isinstance(name, str):
        raise ValueError("derive_column: `name` must be a string")
    s = name.strip()
    if not s:
        raise ValueError("derive_column: `name` cannot be empty")
    if "\x00" in s:
        raise ValueError("derive_column: `name` cannot contain NUL bytes")
    return s


class DeriveColumnStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        name = _validate_column_name(params.get("name"))
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

    def column_dependencies(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        in_cols = input_schemas["in"]
        out: dict[str, ColumnLineage] = {
            c: ColumnLineage(
                sources=[ColumnRef(port="in", column=c)],
                transform="passthrough",
                is_passthrough=True,
            )
            for c in in_cols
        }
        new_name = params.get("name")
        expr = params.get("expression") or ""
        if new_name:
            refs = _extract_column_refs(expr, set(in_cols.keys()))
            out[new_name] = ColumnLineage(
                sources=[ColumnRef(port="in", column=c) for c in refs] or
                        [ColumnRef(port="in", column=c) for c in in_cols.keys()][:0],
                transform="derived from expression",
                expression=expr if len(expr) <= 240 else expr[:237] + "…",
                is_passthrough=False,
            )
        return out


step = DeriveColumnStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

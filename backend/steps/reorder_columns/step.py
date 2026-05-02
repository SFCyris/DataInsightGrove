from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


def _resolve_order(order: list[str], input_cols: list[str]) -> list[str]:
    """Compute the final column order.

    Listed columns that exist in the input come first, in the listed order.
    Unlisted input columns are appended at the end, preserving their input
    order. This keeps the step working when upstream schemas change — adding
    a new column upstream just appends it; renaming or removing one drops it
    from the order list silently.
    """
    seen: set[str] = set()
    result: list[str] = []
    input_set = set(input_cols)
    for c in order:
        if c in input_set and c not in seen:
            result.append(c)
            seen.add(c)
    for c in input_cols:
        if c not in seen:
            result.append(c)
            seen.add(c)
    return result


class ReorderColumnsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        order = params.get("order") or []
        if not order:
            return f"SELECT * FROM {src}"
        # DuckDB's `SELECT a, b, * EXCLUDE (a, b) FROM t` puts a, b first and
        # then everything else (in original input order). This means new
        # columns appearing upstream are auto-appended without requiring the
        # user to update the order list — matches the schema-inference logic
        # in _resolve_order.
        #
        # NOTE: if a listed column doesn't exist upstream, DuckDB's binder
        # will error. The frontend always sends a complete + valid order list
        # (computed from the current preview), and the param form surfaces
        # stale columns when the upstream schema drifts.
        cols_sql = ", ".join(quote_ident(c) for c in order)
        excl_sql = ", ".join(quote_ident(c) for c in order)
        return f"SELECT {cols_sql}, * EXCLUDE ({excl_sql}) FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        in_schema = input_schemas["in"]
        order = params.get("order") or []
        if not order:
            return dict(in_schema)
        final_order = _resolve_order(list(order), list(in_schema.keys()))
        return {c: in_schema[c] for c in final_order}


step = ReorderColumnsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

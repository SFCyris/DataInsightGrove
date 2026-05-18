from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident

_FN_TO_SQL = {
    "sum": "SUM", "mean": "AVG", "min": "MIN", "max": "MAX", "count": "COUNT",
    "rank": "RANK", "row_number": "ROW_NUMBER", "lag": "LAG", "lead": "LEAD",
}


class WindowAggregateStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        fn = params.get("fn") or "sum"
        sql_fn = _FN_TO_SQL.get(fn, fn.upper())
        col = params.get("column")
        alias = quote_ident(params["as"])

        partition = params.get("partitionBy") or []
        order = params.get("orderBy") or []
        partition_clause = (
            f"PARTITION BY {', '.join(quote_ident(c) for c in partition)} " if partition else ""
        )

        # orderBy may be either a list of column names (string form) or a list
        # of {column, direction} dicts — matching sort_rows for UI consistency.
        order_parts: list[str] = []
        for o in order:
            if isinstance(o, dict):
                col_name = o.get("column")
                if not col_name:
                    continue
                direction = (o.get("direction") or "asc").upper()
                if direction not in ("ASC", "DESC"):
                    direction = "ASC"
                order_parts.append(f"{quote_ident(col_name)} {direction}")
            elif isinstance(o, str):
                order_parts.append(quote_ident(o))
        order_clause = f"ORDER BY {', '.join(order_parts)}" if order_parts else ""

        if fn in ("rank", "row_number"):
            expr = f"{sql_fn}() OVER ({partition_clause}{order_clause})"
        elif fn in ("lag", "lead"):
            if not col:
                raise ValueError(f"{fn} requires 'column'")
            expr = f"{sql_fn}({quote_ident(col)}) OVER ({partition_clause}{order_clause})"
        elif fn == "count":
            # count is the only aggregate that supports COUNT(*).
            arg = quote_ident(col) if col else "*"
            expr = f"{sql_fn}({arg}) OVER ({partition_clause}{order_clause})"
        else:
            # Round-8 fix: SUM/MIN/MAX/AVG/STD(*) is invalid SQL. Raise
            # preflight so the editor shows a clear error instead of a
            # cryptic Binder Error.
            if not col:
                raise ValueError(
                    f"window_aggregate: aggregate {fn!r} requires a "
                    "column (count(*) is the only column-less form)",
                )
            expr = f"{sql_fn}({quote_ident(col)}) OVER ({partition_clause}{order_clause})"

        return f"SELECT *, {expr} AS {alias} FROM {src}"

    def infer_schema(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        alias = params.get("as")
        if alias:
            fn = params.get("fn", "sum")
            if fn in ("count", "rank", "row_number"):
                s[alias] = "integer"
            else:
                s[alias] = "double"
        return s


step = WindowAggregateStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

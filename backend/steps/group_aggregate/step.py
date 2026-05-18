from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import ColumnLineage, ColumnRef, Step, quote_ident

_FN_TO_SQL = {
    "sum": "SUM",
    "mean": "AVG",
    "min": "MIN",
    "max": "MAX",
    "count": "COUNT",
    "count_distinct": "COUNT(DISTINCT %s)",
    "std": "STDDEV",
}


class GroupAggregateStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        group_by = params.get("groupBy") or []
        aggregates = params.get("aggregates") or []
        if not group_by and not aggregates:
            return f"SELECT * FROM {src}"

        group_cols = [quote_ident(c) for c in group_by]
        agg_exprs: list[str] = []
        for a in aggregates:
            fn = a.get("fn", "sum")
            col = a.get("column")
            alias = a.get("as") or (f"{fn}_{col}" if col else fn)
            if fn == "count" and not col:
                expr = "COUNT(*)"
            elif fn == "count_distinct" and col:
                expr = f"COUNT(DISTINCT {quote_ident(col)})"
            else:
                # Round-8 fix: previously, an aggregate with a non-count
                # fn but no ``column`` fell through to ``f"{sql_fn}(*)"``
                # which DuckDB rejects ("SUM(*)" is invalid syntax). Raise
                # a clear ValueError preflight so the editor surfaces it
                # instead of a cryptic Binder Error at run time.
                if not col:
                    raise ValueError(
                        f"group_aggregate: aggregate {fn!r} requires a "
                        f"column (got alias={alias!r}, column is empty)",
                    )
                sql_fn = _FN_TO_SQL.get(fn, fn.upper())
                expr = f"{sql_fn}({quote_ident(col)})"
            agg_exprs.append(f"{expr} AS {quote_ident(alias)}")

        select_list = ", ".join(group_cols + agg_exprs)
        if group_cols:
            return f"SELECT {select_list} FROM {src} GROUP BY {', '.join(group_cols)}"
        return f"SELECT {select_list} FROM {src}"

    def infer_schema(self, input_schemas, params):
        in_schema = input_schemas.get("in", {})
        out: dict[str, str] = {}
        for c in params.get("groupBy") or []:
            out[c] = in_schema.get(c, "unknown")
        for a in params.get("aggregates") or []:
            alias = a.get("as") or (f"{a.get('fn','sum')}_{a.get('column','')}".strip("_") or a.get("fn","value"))
            fn = a.get("fn")
            if fn in ("count", "count_distinct"):
                out[alias] = "integer"
            else:
                out[alias] = "double"
        return out

    def column_dependencies(self, input_schemas, params):
        in_schema = input_schemas.get("in", {})
        out: dict[str, ColumnLineage] = {}
        # Group-by columns flow through the aggregation by name; they're
        # passthrough in the column-flow sense (the values become the
        # group key, but the column identity is preserved).
        for c in params.get("groupBy") or []:
            if c in in_schema:
                out[c] = ColumnLineage(
                    sources=[ColumnRef(port="in", column=c)],
                    transform="group key",
                    expression=None,
                    is_passthrough=True,
                )
        # Aggregate output columns derive from the source column with the
        # aggregation function applied. count(*) has no source column.
        for a in params.get("aggregates") or []:
            fn = a.get("fn", "sum")
            col = a.get("column")
            alias = a.get("as") or (f"{fn}_{col}" if col else fn)
            sources = (
                [ColumnRef(port="in", column=col)]
                if col and col in in_schema
                else []
            )
            expr = f"{fn.upper()}({col})" if col else f"{fn.upper()}(*)"
            out[alias] = ColumnLineage(
                sources=sources,
                transform=f"aggregate ({fn})",
                expression=expr,
                is_passthrough=False,
            )
        return out


step = GroupAggregateStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

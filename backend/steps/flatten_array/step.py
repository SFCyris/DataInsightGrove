"""flatten_array — reshape nested array columns.

Three modes, each compiled to DuckDB SQL:
  - flatten_one_level → list_flatten(col)
  - fully_flatten     → recursive list_flatten via list_reduce; collapses
                        any nesting depth down to a single flat list
  - unnest_to_rows    → UNNEST(col); other columns repeat per element

Browser parity: DuckDB-WASM ships list_flatten and unnest, so the same
SQL runs unchanged in the live preview. The unnest_to_rows mode does
change row count, which the preview engine handles via its standard
sample-then-render path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class FlattenArrayStep(Step):
    def to_sql(
        self,
        params: dict[str, Any],
        inputs: dict[str, str],
        *,
        input_schemas: dict[str, dict[str, str]] | None = None,
    ) -> str:
        src = inputs["in"]
        arr = quote_ident(params["arrayColumn"])
        mode = (params.get("mode") or "flatten_one_level").lower()
        out_name = params.get("outputColumn") or params["arrayColumn"]
        out = quote_ident(out_name)
        keep_empty = bool(params.get("keepEmpty", False))

        if mode == "flatten_one_level":
            # list_flatten([[1,2],[3]]) → [1,2,3]
            return self._project_replacing(
                src, arr, out_name,
                f"list_flatten({arr})",
                input_schemas,
            )

        if mode == "fully_flatten":
            # No native deep-flatten in DuckDB; iterate with a fixed bound
            # (8 levels covers any pathological structure we'd see in
            # practice — stops short of stack overflow on cycles, which
            # arrays can't have anyway).
            expr = arr
            for _ in range(8):
                # COALESCE keeps the value unchanged when list_flatten
                # is a no-op (the inner element isn't itself a list).
                expr = f"coalesce(try_cast(list_flatten({expr}) AS ANY[]), {expr})"
            return self._project_replacing(
                src, arr, out_name, expr, input_schemas,
            )

        # unnest_to_rows: emit one row per element, repeat other columns.
        # DuckDB's UNNEST inside a SELECT projects each element to a row.
        # The other columns repeat via the implicit cross-join semantics
        # of UNNEST in the projection.
        if input_schemas and "in" in input_schemas:
            other_cols = [
                quote_ident(c) for c in input_schemas["in"].keys()
                if c != params["arrayColumn"]
            ]
            other_select = ", ".join(other_cols) if other_cols else ""
            sep = ", " if other_select else ""
            unnest_expr = f"UNNEST({arr}) AS {out}"
            base = f"SELECT {other_select}{sep}{unnest_expr} FROM {src}"
        else:
            # Schema unavailable — use SELECT * EXCLUDE to drop the
            # source array column, then add the unnested scalar.
            base = (
                f"SELECT * EXCLUDE ({arr}), UNNEST({arr}) AS {out} "
                f"FROM {src}"
            )

        if keep_empty:
            # UNNEST(NULL) and UNNEST([]) both drop the row by default.
            # To keep them, replace empties with [NULL] so the row
            # survives with a NULL output value. cardinality() returns
            # 0 for empty arrays and NULL for NULL arrays — coalesce
            # treats both identically.
            null_guarded_arr = (
                f"CASE WHEN coalesce(cardinality({arr}), 0) = 0 "
                f"THEN [NULL] ELSE {arr} END"
            )
            base = base.replace(f"UNNEST({arr})", f"UNNEST({null_guarded_arr})")

        return base

    def _project_replacing(
        self,
        src: str,
        arr_quoted: str,
        out_name: str,
        new_expr: str,
        input_schemas: dict[str, dict[str, str]] | None,
    ) -> str:
        """Project all columns, replacing the source array column with
        ``new_expr`` aliased as ``out_name``. When out_name == source,
        the column is overwritten in place; when different, a new
        column is added and the source kept."""
        out_quoted = quote_ident(out_name)
        if input_schemas and "in" in input_schemas:
            in_cols = list(input_schemas["in"].keys())
            parts = []
            for c in in_cols:
                cq = quote_ident(c)
                if cq == arr_quoted and out_name == c:
                    parts.append(f"{new_expr} AS {out_quoted}")
                else:
                    parts.append(cq)
            if out_quoted not in {quote_ident(c) for c in in_cols}:
                parts.append(f"{new_expr} AS {out_quoted}")
            return f"SELECT {', '.join(parts)} FROM {src}"
        # Schema fallback: keep arr as a new column and original.
        return f"SELECT *, {new_expr} AS {out_quoted} FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        in_schema = input_schemas["in"]
        mode = (params.get("mode") or "flatten_one_level").lower()
        arr_name = params.get("arrayColumn")
        out_name = params.get("outputColumn") or arr_name
        if not arr_name:
            return dict(in_schema)

        if mode in ("flatten_one_level", "fully_flatten"):
            # Output remains an array column; type stays "array" /
            # whatever the source's logical type was. We don't try to
            # collapse element-type nesting in the schema string.
            elem_type = in_schema.get(arr_name, "array")
            if arr_name == out_name:
                return {**in_schema, arr_name: elem_type}
            return {**in_schema, out_name: elem_type}

        # unnest_to_rows: replace the array column with its element type
        # (unknown — we can't statically infer it from the schema dict).
        if mode == "unnest_to_rows":
            result = {k: v for k, v in in_schema.items() if k != arr_name}
            result[out_name] = "unknown"
            return result
        return dict(in_schema)


step = FlattenArrayStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

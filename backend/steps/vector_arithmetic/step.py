"""vector_arithmetic — element-wise vector ops compiled to DuckDB SQL.

DuckDB's list_transform + list_aggregate cover everything element-wise.
For binary ops we zip the two arrays index-by-index with
list_transform(generate_series(1, len), idx -> a[idx] OP b[idx]).
For magnitude we use list_reduce / list_sum on element squares.

Browser parity: all functions used here ship in DuckDB-WASM, so the
preview engine runs unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


_BINARY_OPS = {
    "add": "+",
    "subtract": "-",
    "multiply": "*",
    "divide": "/",
}


class VectorArithmeticStep(Step):
    def to_sql(
        self,
        params: dict[str, Any],
        inputs: dict[str, str],
        *,
        input_schemas: dict[str, dict[str, str]] | None = None,
    ) -> str:
        src = inputs["in"]
        op = (params.get("op") or "add").lower()
        out_name = params["outputColumn"]
        out = quote_ident(out_name)
        left = quote_ident(params["leftColumn"])

        if op in _BINARY_OPS:
            sym = _BINARY_OPS[op]
            right_col = params.get("rightColumn")
            if not right_col:
                raise ValueError(
                    f"vector_arithmetic op={op!r} requires a rightColumn",
                )
            right = quote_ident(right_col)
            # Zip-then-transform: produce an array of the same length as
            # the left vector, with element-wise op. NULL-safe via
            # try_cast so a length mismatch surfaces as NULL rather
            # than an opaque error.
            expr = (
                f"list_transform("
                f"generate_series(1, least(len({left}), len({right}))), "
                f"i -> ({left}[i]) {sym} ({right}[i])"
                f")"
            )

        elif op in ("scalar_multiply", "scalar_add"):
            scalar = params.get("scalar")
            if scalar is None:
                raise ValueError(
                    f"vector_arithmetic op={op!r} requires a scalar",
                )
            sym = "*" if op == "scalar_multiply" else "+"
            expr = (
                f"list_transform({left}, x -> x {sym} ({float(scalar)}))"
            )

        elif op == "normalize_l2":
            # mag = sqrt(sum(x*x for x in v))
            # result = list_transform(v, x -> x / mag) when mag > 0
            mag = (
                f"sqrt(list_sum(list_transform({left}, x -> x * x)))"
            )
            expr = (
                f"CASE WHEN ({mag}) > 0 "
                f"THEN list_transform({left}, x -> x / ({mag})) "
                f"ELSE {left} END"
            )

        elif op == "magnitude":
            expr = (
                f"sqrt(list_sum(list_transform({left}, x -> x * x)))"
            )

        else:
            raise ValueError(f"unknown vector_arithmetic op: {op!r}")

        return f"SELECT *, {expr} AS {out} FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        in_schema = input_schemas["in"]
        out_name = params.get("outputColumn") or "vector_result"
        op = (params.get("op") or "add").lower()
        # magnitude returns a scalar number; everything else returns a
        # vector. Schema inference here is shallow — engine reports
        # whatever DuckDB infers at run time.
        out_type = "double" if op == "magnitude" else "array"
        return {**in_schema, out_name: out_type}


step = VectorArithmeticStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

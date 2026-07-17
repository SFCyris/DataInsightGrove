from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import ColumnLineage, ColumnRef, Step, quote_ident

_TYPE_TO_SQL = {
    # ── Base physical types ────────────────────────────────────────────
    "integer":  "BIGINT",
    "double":   "DOUBLE",
    "string":   "VARCHAR",
    "boolean":  "BOOLEAN",
    "date":     "DATE",
    "datetime": "TIMESTAMP",
    # ── Meta-types ─────────────────────────────────────────────────────
    # Where DuckDB has a native physical type that's a better fit than
    # DOUBLE/VARCHAR, we use it. The trade-offs:
    #
    #   currency, percentage  → DECIMAL  (exact decimal arithmetic; no
    #     floating-point drift like 0.1+0.2≠0.3 on DOUBLE).
    #   uuid                  → UUID    (DuckDB's 128-bit native UUID;
    #     compares + sorts faster than VARCHAR; binary on disk).
    #   bignum                → HUGEINT (128-bit signed int; covers hex
    #     values that overflow BIGINT, e.g. SHA-256 fragments).
    #   scientific            → DOUBLE  (for now; range-aware storage in
    #     the multi-storage detection step picks VARCHAR when values
    #     exceed ±1.8e308).
    #
    # Anything that's semantically a string keeps VARCHAR — leading-zero
    # phone numbers, email addresses, IANA timezones, etc.
    "index":          "BIGINT",
    "percentage":     "DECIMAL(9,6)",     # 0.123456 fits; ≤999.999999 absolute
    "currency":       "DECIMAL(18,4)",    # ±99,999,999,999,999.9999 — fits any
                                          # realistic monetary value, exact math
    "scientific":     "DOUBLE",           # IEEE 754; 1.2 promotes to VARCHAR
                                          # for out-of-range values
    "hex":            "VARCHAR",          # text notation; bignum below for the
                                          # numeric-decoded form
    "bignum":         "HUGEINT",          # 128-bit, ±170,141,183,460,469,231,
                                          # 731,687,303,715,884,105,727
    "decimal_string": "VARCHAR",          # arbitrary precision; lexical decimal
                                          # storage when DECIMAL/HUGEINT overflow
    # ── Composite + spatial types ──────────────────────────────────────
    "json":           "JSON",             # DuckDB native JSON
    "array":          "JSON",             # variable-length list, JSON-encoded
    "vector":         "DOUBLE[]",         # fixed-length numeric array (DuckDB
                                          # array_cosine_similarity / kNN compatible)
    "cartesian2d":    "STRUCT(x DOUBLE, y DOUBLE)",
    "cartesian3d":    "STRUCT(x DOUBLE, y DOUBLE, z DOUBLE)",
    "polar2d":        "STRUCT(r DOUBLE, theta DOUBLE)",
    "polar3d":        "STRUCT(r DOUBLE, theta DOUBLE, phi DOUBLE)",
    "geographic":     "GEOMETRY",         # DuckDB spatial extension
    "uuid":           "UUID",             # native DuckDB UUID, not VARCHAR
    "email":          "VARCHAR",
    "url":            "VARCHAR",
    "ip":             "VARCHAR",
    "phone":          "VARCHAR",
    "country":        "VARCHAR",
    "color":          "VARCHAR",
    "timezone":       "VARCHAR",
    # decimal_string uses VARCHAR storage for
    # arbitrary-precision decimals beyond DECIMAL's 38-digit limit.
}


class CastTypeStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = params["column"]
        target = params["targetType"]
        strict = params.get("strict", False)
        # Round-8 fix: previously did ``_TYPE_TO_SQL[target]`` which raises
        # a bare ``KeyError`` on unknown target types — legacy pipelines
        # referencing a removed type, or a manifest enum typo, crashed
        # mid-compile with no clear error. Return a ValueError naming the
        # allowed values instead.
        sql_type = _TYPE_TO_SQL.get(target)
        if sql_type is None:
            allowed = ", ".join(sorted(_TYPE_TO_SQL.keys()))
            raise ValueError(
                f"cast_type: unknown targetType {target!r}; "
                f"expected one of: {allowed}",
            )
        cast_op = "CAST" if strict else "TRY_CAST"
        col_q = quote_ident(col)
        return f"SELECT * REPLACE ({cast_op}({col_q} AS {sql_type}) AS {col_q}) FROM {src}"

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        col = params.get("column")
        target = params.get("targetType")
        if col and col in s and target:
            s[col] = target
        return s

    def column_dependencies(self, input_schemas, params):
        in_schema = input_schemas.get("in", {})
        target_col = params.get("column")
        target_type = params.get("targetType")
        out: dict[str, ColumnLineage] = {}
        for c in in_schema:
            if c == target_col and target_type:
                out[c] = ColumnLineage(
                    sources=[ColumnRef(port="in", column=c)],
                    transform=f"cast to {target_type}",
                    expression=None,
                    is_passthrough=False,
                )
            else:
                out[c] = ColumnLineage(
                    sources=[ColumnRef(port="in", column=c)],
                    transform="passthrough",
                    expression=None,
                    is_passthrough=True,
                )
        return out

    def nan_origin_sql(
        self, params: dict[str, Any], inputs: dict[str, str],
    ) -> tuple[str, str] | None:
        """Row-index enumerator for cells that became NULL via TRY_CAST.

        Returns (column_name, sql) where the SQL produces a single column
        `row_index` of zero-based positions. The executor calls this on
        the upstream CTE chain, converts the rows into a `NanOrigin` with
        `cause="cast_failure"`, and attaches it to the producing node.
        """
        col = params.get("column")
        target = params.get("targetType")
        if not col or not target or target not in _TYPE_TO_SQL:
            return None
        src = inputs.get("in")
        if not src:
            return None
        col_q = quote_ident(col)
        sql_type = _TYPE_TO_SQL[target]
        sql = (
            f"SELECT (row_number() OVER () - 1) AS row_index FROM {src} "
            f"WHERE {col_q} IS NOT NULL "
            f"AND TRY_CAST({col_q} AS {sql_type}) IS NULL"
        )
        return (col, sql)

    def validation_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str | None:
        """Count cast outcomes by comparing pre-cast input to a re-applied
        TRY_CAST. The executor runs this against the upstream CTE chain
        and attaches the result to the run as an artifact.

        Reports four counts:
          - total: rows in the input
          - source_null: input was already NULL (cast didn't lose anything)
          - cast_failures: input was non-null but became NULL via TRY_CAST
                           (precision loss / overflow / shape mismatch)
          - source_non_null: input was non-null (sanity baseline)
        """
        col = params.get("column")
        target = params.get("targetType")
        if not col or not target or target not in _TYPE_TO_SQL:
            return None
        src = inputs.get("in")
        if not src:
            return None
        col_q = quote_ident(col)
        sql_type = _TYPE_TO_SQL[target]
        return (
            f"SELECT "
            f"COUNT(*) AS total, "
            f"COUNT(*) FILTER (WHERE {col_q} IS NULL) AS source_null, "
            f"COUNT(*) FILTER (WHERE {col_q} IS NOT NULL) AS source_non_null, "
            f"COUNT(*) FILTER (WHERE {col_q} IS NOT NULL AND TRY_CAST({col_q} AS {sql_type}) IS NULL) "
            f"AS cast_failures "
            f"FROM {src}"
        )


step = CastTypeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

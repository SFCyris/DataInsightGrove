from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident

_TYPE_TO_SQL = {
    "integer": "BIGINT",
    "double": "DOUBLE",
    "string": "VARCHAR",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    # Meta-types — physical storage is the same as their base type, but the
    # logical-type label travels through the schema and lights up special
    # rendering / validation in the grid. The full registry of meta-types
    # (with detectors + descriptions) lives in dig.engine.meta_types:TYPES.
    # Any new entry there should be mirrored here.
    "index":       "BIGINT",
    "percentage":  "DOUBLE",
    "currency":    "DOUBLE",
    "scientific":  "DOUBLE",
    "hex":         "VARCHAR",
    "uuid":        "VARCHAR",
    "email":       "VARCHAR",
    "url":         "VARCHAR",
    "ip":          "VARCHAR",
    "phone":       "VARCHAR",
    "country":     "VARCHAR",
    "color":       "VARCHAR",
    "timezone":    "VARCHAR",
}


class CastTypeStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = params["column"]
        target = params["targetType"]
        strict = params.get("strict", False)
        sql_type = _TYPE_TO_SQL[target]
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


step = CastTypeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

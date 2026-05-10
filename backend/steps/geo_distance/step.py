from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident

# Mean Earth radius in metres. Haversine treats Earth as a perfect sphere
# (vs WGS84 ellipsoid which would give ~0.5% accuracy improvement). For
# typical "stores within 5 km of customer" use cases, sphere is fine.
_EARTH_R_M = 6_371_000.0


class GeoDistanceStep(Step):
    """Haversine great-circle distance, expressed entirely in DuckDB SQL
    so it runs unchanged in the browser preview and on the backend.

    Formula:
      a = sin²(Δφ/2) + cos(φ1)·cos(φ2)·sin²(Δλ/2)
      c = 2·atan2(√a, √(1−a))
      d = R · c     (in metres, R = 6,371,000)
    """

    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        lat1 = quote_ident(params["lat1Column"])
        lon1 = quote_ident(params["lon1Column"])
        lat2 = quote_ident(params["lat2Column"])
        lon2 = quote_ident(params["lon2Column"])
        out  = params["outputColumn"]
        if not isinstance(out, str) or not out:
            raise ValueError("outputColumn is required")

        # Convert to radians inline. RADIANS() exists in DuckDB.
        # The expression is wrapped in CASE to return NULL on any NULL input
        # (DuckDB would normally propagate NULL, but the nested arithmetic
        # has CAST risk if a column carries strings).
        expr = (
            f"CASE WHEN {lat1} IS NULL OR {lon1} IS NULL OR {lat2} IS NULL OR {lon2} IS NULL THEN NULL "
            f"ELSE {_EARTH_R_M} * 2 * ASIN(SQRT("
            f"  POWER(SIN(RADIANS(({lat2}::DOUBLE - {lat1}::DOUBLE) / 2)), 2) "
            f"  + COS(RADIANS({lat1}::DOUBLE)) * COS(RADIANS({lat2}::DOUBLE)) "
            f"  * POWER(SIN(RADIANS(({lon2}::DOUBLE - {lon1}::DOUBLE) / 2)), 2)"
            f")) END"
        )
        return f"SELECT *, {expr} AS {quote_ident(out)} FROM {src}"

    def infer_schema(
        self, input_schemas: dict[str, dict[str, str]], params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        out = params.get("outputColumn")
        if out:
            s[str(out)] = "double"
        return s


step = GeoDistanceStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

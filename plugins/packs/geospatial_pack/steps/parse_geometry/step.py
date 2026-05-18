"""parse_geometry — text → shapely geometry.

Geometry is stored on the Polars frame as a WKB-bytes column so it
survives parquet round-tripping and stays compact. Downstream steps
(spatial_join, etc.) re-hydrate via shapely.from_wkb.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _parse_one(raw: str | None, fmt: str) -> tuple[bytes | None, str | None, bool]:
    """Return (wkb_bytes, geometry_type, valid)."""
    from shapely import wkb, wkt
    from shapely.geometry import shape as _shape

    if raw is None or not str(raw).strip():
        return (None, None, False)
    s = str(raw).strip()
    chosen = fmt
    if chosen == "auto":
        chosen = "geojson" if s.startswith("{") else "wkt"
    try:
        if chosen == "wkt":
            geom = wkt.loads(s)
        else:
            obj = json.loads(s)
            # Accept either Feature wrapper or bare Geometry.
            if isinstance(obj, dict) and obj.get("type") == "Feature":
                obj = obj.get("geometry") or {}
            geom = _shape(obj)
        return (wkb.dumps(geom), geom.geom_type, geom.is_valid)
    except Exception:
        return (None, None, False)


class ParseGeometryStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        src = params["sourceColumn"]
        fmt = (params.get("format") or "auto").lower()
        prefix = params.get("outputPrefix") or ""

        if src not in df.columns:
            raise ValueError(
                f"parse_geometry: source column {src!r} not found",
            )

        wkbs: list[bytes | None] = []
        types: list[str | None] = []
        valids: list[bool] = []
        for raw in df[src].to_list():
            wkb_bytes, gtype, valid = _parse_one(raw, fmt)
            wkbs.append(wkb_bytes)
            types.append(gtype)
            valids.append(valid)

        out_df = df.with_columns([
            pl.Series(f"{prefix}geometry", wkbs),
            pl.Series(f"{prefix}geometry_type", types),
            pl.Series(f"{prefix}geometry_valid", valids),
        ])
        return PolarsResult(output=out_df)


step = ParseGeometryStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

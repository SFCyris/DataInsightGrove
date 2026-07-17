"""geohash_cell — encode lat/lon as a spatial-index cell id.

Two systems supported:
  - geohash: classic base-32 hashing (geohash2 library). Cell shape is
    a lat/lon rectangle that shrinks per character.
  - h3: Uber's hexagonal grid (h3 library). Equal-area hexes at every
    resolution; better for heatmaps and visual aggregation.

Output is a string column the user can group_by directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class GeohashCellStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        lat_col = params["latColumn"]
        lon_col = params["lonColumn"]
        system = (params.get("system") or "h3").lower()
        precision = int(params.get("precision", 7))
        out_name = params["outputColumn"]

        if lat_col not in df.columns:
            raise ValueError(f"geohash_cell: latColumn {lat_col!r} not found")
        if lon_col not in df.columns:
            raise ValueError(f"geohash_cell: lonColumn {lon_col!r} not found")

        lats = df[lat_col].to_list()
        lons = df[lon_col].to_list()

        cells: list[str | None]
        if system == "geohash":
            import geohash2
            # geohash2 expects (lat, lon, precision).
            cells = []
            for la, lo in zip(lats, lons):
                if la is None or lo is None:
                    cells.append(None)
                    continue
                try:
                    cells.append(geohash2.encode(float(la), float(lo), precision=precision))
                except Exception:
                    cells.append(None)
        elif system == "h3":
            import h3
            cells = []
            for la, lo in zip(lats, lons):
                if la is None or lo is None:
                    cells.append(None)
                    continue
                try:
                    cells.append(h3.latlng_to_cell(float(la), float(lo), precision))
                except Exception:
                    cells.append(None)
        else:
            raise ValueError(f"geohash_cell: unknown system {system!r}")

        out_df = df.with_columns(pl.Series(out_name, cells))
        return PolarsResult(output=out_df)


step = GeohashCellStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

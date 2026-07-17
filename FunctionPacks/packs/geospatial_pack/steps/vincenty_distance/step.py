"""vincenty_distance — geodesic distance via geographiclib.

Modern geographiclib uses Karney's improved algorithm (the "Geodesic"
class), which converges where Vincenty's original formula diverges
(near antipodes). The label "Vincenty" stays for user familiarity —
the math underneath is strictly more robust.

Output is metres. Optional output adds the initial bearing in degrees
(0 = north, 90 = east).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class VincentyDistanceStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from geographiclib.geodesic import Geodesic

        df = inputs["in"]
        cols = {
            "lat1": params["lat1Column"],
            "lon1": params["lon1Column"],
            "lat2": params["lat2Column"],
            "lon2": params["lon2Column"],
        }
        for k, c in cols.items():
            if c not in df.columns:
                raise ValueError(
                    f"vincenty_distance: column for {k} ({c!r}) not found",
                )
        out_name = params["outputColumn"]
        emit_bearing = bool(params.get("outputBearing", False))

        geod = Geodesic.WGS84
        lat1s = df[cols["lat1"]].to_list()
        lon1s = df[cols["lon1"]].to_list()
        lat2s = df[cols["lat2"]].to_list()
        lon2s = df[cols["lon2"]].to_list()

        distances: list[float | None] = []
        bearings: list[float | None] = []
        for la1, lo1, la2, lo2 in zip(lat1s, lon1s, lat2s, lon2s):
            if None in (la1, lo1, la2, lo2):
                distances.append(None)
                bearings.append(None)
                continue
            try:
                r = geod.Inverse(float(la1), float(lo1), float(la2), float(lo2))
                distances.append(float(r["s12"]))
                # Normalise bearing to [0, 360).
                bearings.append((float(r["azi1"]) + 360.0) % 360.0)
            except Exception:
                distances.append(None)
                bearings.append(None)

        new_cols = [pl.Series(out_name, distances)]
        if emit_bearing:
            new_cols.append(pl.Series(f"{out_name}_bearing", bearings))
        out_df = df.with_columns(new_cols)
        return PolarsResult(output=out_df)


step = VincentyDistanceStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

"""map_match — snap input points to the nearest point in a reference table."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    R = 6371000.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class MapMatchStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from scipy.spatial import cKDTree
        import numpy as np

        in_df = inputs["in"]
        ref_df = inputs["reference"]
        lat = params["latColumn"]; lon = params["lonColumn"]
        rlat = params["refLatColumn"]; rlon = params["refLonColumn"]; rid = params["refIdColumn"]
        out_id = params.get("matchedIdColumn") or "matched_id"
        out_d = params.get("matchedDistanceColumn") or "matched_distance_m"

        for col_name, col_val, src in (("latColumn", lat, "in"), ("lonColumn", lon, "in"),
                                          ("refLatColumn", rlat, "reference"),
                                          ("refLonColumn", rlon, "reference"),
                                          ("refIdColumn", rid, "reference")):
            target_df = in_df if src == "in" else ref_df
            if col_val not in target_df.columns:
                raise ValueError(f"map_match: {col_name} {col_val!r} not found in {src} input")

        ref_lats = np.asarray(ref_df[rlat].to_list(), dtype=float)
        ref_lons = np.asarray(ref_df[rlon].to_list(), dtype=float)
        ref_ids = ref_df[rid].to_list()
        if len(ref_lats) == 0:
            raise ValueError("map_match: reference table is empty")

        # Build KD-tree on a 3-D ECEF projection so nearest-neighbour
        # queries are spherically meaningful (a 2-D KD-tree on lat/lon
        # would be wrong near the poles + at the antimeridian).
        def _to_ecef(la, lo):
            la_r = np.radians(la); lo_r = np.radians(lo)
            return np.cos(la_r) * np.cos(lo_r), np.cos(la_r) * np.sin(lo_r), np.sin(la_r)
        rx, ry, rz = _to_ecef(ref_lats, ref_lons)
        tree = cKDTree(np.column_stack([rx, ry, rz]))

        in_lats = in_df[lat].to_list()
        in_lons = in_df[lon].to_list()
        matched_id: list[Any] = []
        matched_d: list[float | None] = []
        for la, lo in zip(in_lats, in_lons):
            if la is None or lo is None:
                matched_id.append(None); matched_d.append(None); continue
            la_f = float(la); lo_f = float(lo)
            la_r = math.radians(la_f); lo_r = math.radians(lo_f)
            q = (math.cos(la_r) * math.cos(lo_r),
                  math.cos(la_r) * math.sin(lo_r),
                  math.sin(la_r))
            _, idx = tree.query(q, k=1)
            matched_id.append(ref_ids[idx])
            matched_d.append(_haversine_m(la_f, lo_f, float(ref_lats[idx]), float(ref_lons[idx])))

        out_df = in_df.with_columns([
            pl.Series(out_id, matched_id),
            pl.Series(out_d, matched_d),
        ])
        return PolarsResult(output=out_df)


step = MapMatchStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

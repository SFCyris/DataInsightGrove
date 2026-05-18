"""Boundary lookup: US city → approximate WKB geometry.

Accepts:
  - A plain city name (``"Boise"``) — returns the largest match by area
    if multiple states have a city by that name (e.g. Springfield).
  - A ``"City, ST"`` combo (``"Boise, ID"``) — disambiguates.
  - A lat/lon point — point-in-polygon over the synthetic equal-area
    circles. Best-effort; may return None at city granularity since
    circles don't tile the country.

Reference data: us_places_2023.parquet — 32,329 rows derived from the
Census Bureau's 2023 Places gazetteer (Incorporated Places + CDPs).
Public domain. Boundaries are equal-area circles around the gazetteer
centroid, sized by the true land area — useful for marker-style maps
and city-scale visualisation, NOT a substitute for the real TIGER
Place shapefile if pixel-accurate boundaries matter.

Disambiguation: when an unqualified name matches multiple cities (e.g.
"Springfield"), the largest-area match wins. To resolve a specific
city, supply ``"Springfield, IL"`` (the lookup key is built with both
forms).
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.extensions.pack_data import pack_data

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))
from _lookup_common import (  # noqa: E402
    load_reference, resolve_row, output_columns_for,
)


# ``name_state`` ("Boise, ID") wins over bare ``name`` so a fully-
# qualified input doesn't get clobbered by a same-name place in a
# different state.
_KEY_ORDER = ["name_state", "name"]

# Single-name lookup uses a per-name "biggest place by area" index;
# the underlying parquet has duplicate names. We post-process the
# dataset's ``by_key["name"]`` after the standard build.
_POSTPROCESS_LOCK = threading.Lock()
_POSTPROCESSED: set[int] = set()


def _get_dataset():
    ds = load_reference(
        pack_data("geospatial_pack", "us_places_2023"),
        key_columns={"name": "name", "name_state": "name_state"},
    )
    # Round-2 fix: the default `load_reference` indexes by inserting
    # rows in order — so the FIRST row with a given name wins, which
    # is alphabetical by state (Alabama). Override the ``name`` index
    # to prefer the largest-area row, so ``Springfield`` resolves to
    # the IL one (Illinois state capital, ~155 km²) rather than the
    # AL one. The ``name_state`` index keeps every state-qualified
    # match.
    cache_id = id(ds)
    if cache_id in _POSTPROCESSED:
        return ds
    with _POSTPROCESS_LOCK:
        if cache_id in _POSTPROCESSED:
            return ds
        name_idx = ds.by_key.get("name") or {}
        areas = ds.df["land_area_m2"].to_list()
        names = ds.df["name"].to_list()
        best: dict[str, tuple[int, float]] = {}
        for i, n in enumerate(names):
            if n is None:
                continue
            key = str(n).strip().upper()
            area = float(areas[i] or 0.0)
            current = best.get(key)
            if current is None or area > current[1]:
                best[key] = (i, area)
        for key, (i, _area) in best.items():
            name_idx[key] = i
        _POSTPROCESSED.add(cache_id)
        return ds


class WkbByUsCityStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        mode = params.get("input_mode") or "auto"
        out_col = params.get("output_column") or "city_geometry"
        input_col = params.get("input_column")
        lat_col = params.get("lat_column")
        lon_col = params.get("lon_column")

        text_vals = df[input_col].to_list() if input_col and input_col in df.columns else [None] * df.height
        lat_vals = df[lat_col].to_list() if lat_col and lat_col in df.columns else [None] * df.height
        lon_vals = df[lon_col].to_list() if lon_col and lon_col in df.columns else [None] * df.height

        dataset = _get_dataset()
        indices: list[int | None] = [
            resolve_row(
                dataset,
                input_mode=mode,
                text_value=text_vals[i],
                lat=lat_vals[i],
                lon=lon_vals[i],
                key_order=_KEY_ORDER,
            )
            for i in range(df.height)
        ]

        out = output_columns_for(
            dataset.df,
            indices,
            output_column=out_col,
            metadata_columns={
                "name": "name",
                "state": "state",
                "place_type": "place_type",
                "centroid_lat": "centroid_lat",
                "centroid_lon": "centroid_lon",
            },
        )
        result_df = df.with_columns([pl.Series(name, vals) for name, vals in out.items()])
        matched = sum(1 for i in indices if i is not None)
        return PolarsResult(
            output=result_df,
            artifacts=[{
                "kind": "lookup_summary",
                "label": "🏙 US city boundary lookup",
                "rows": df.height,
                "matched": matched,
                "unmatched": df.height - matched,
                "note": "Boundaries are equal-area circles around the gazetteer centroid — approximate.",
            }],
        )

    def infer_schema(self, input_schemas, params):
        s = dict(input_schemas.get("in", {}))
        out_col = params.get("output_column") or "city_geometry"
        s[out_col] = "blob"
        s[f"{out_col}_name"] = "string"
        s[f"{out_col}_state"] = "string"
        s[f"{out_col}_place_type"] = "string"
        s[f"{out_col}_centroid_lat"] = "double"
        s[f"{out_col}_centroid_lon"] = "double"
        return s


step = WkbByUsCityStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

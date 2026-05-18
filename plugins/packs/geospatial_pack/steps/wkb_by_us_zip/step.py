"""Boundary lookup: US ZIP / ZCTA → approximate WKB geometry.

Accepts a 5-digit US ZIP (case-insensitive, ZIP+4 tolerated — the
trailing +4 is stripped before lookup) or a lat/lon point. Returns
an approximate equal-area circular polygon around the ZCTA's centroid
sized by its true land area from the Census gazetteer.

Boundary accuracy: the bundled data is centroid + land area only.
Boundaries are 32-vertex circles with the gazetteer's area — useful
for marker-style maps, dot-density, and rough choropleth, but NOT a
substitute for the real ZCTA shapefile if pixel-accurate boundaries
matter. To use real polygons, replace ``us_zcta_centroids_2023.parquet``
with a parquet whose ``geometry_wkb`` column holds the real shapes.

Reference data: us_zcta_centroids_2023.parquet — 33,791 rows derived
from the Census Bureau's 2023 ZCTA gazetteer. Public domain.
"""
from __future__ import annotations

import json
import sys
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


_KEY_ORDER = ["zip"]


def _normalize_zip(value: Any) -> Any:
    """Strip a ZIP+4 suffix and pad to 5 digits.

    Accepts ``"02139"``, ``"02139-1234"``, ``"2139"`` (missing leading zero)
    and integer inputs like ``2139``. Returns the canonical 5-digit
    string for index lookup, or None if it can't be normalised.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if "-" in s:
        s = s.split("-", 1)[0]
    # Drop a trailing "+4" written without a hyphen (rare but possible).
    if len(s) > 5 and s[5:].lstrip("0") == "":
        s = s[:5]
    # Numeric input → pad to 5.
    if s.isdigit():
        return s.zfill(5)
    return s


def _get_dataset():
    return load_reference(
        pack_data("geospatial_pack", "us_zcta_centroids_2023"),
        key_columns={"zip": "zip"},
    )


class WkbByUsZipStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        mode = params.get("input_mode") or "auto"
        out_col = params.get("output_column") or "zip_geometry"
        input_col = params.get("input_column")
        lat_col = params.get("lat_column")
        lon_col = params.get("lon_column")

        # Normalise ZIPs in Python (the index keys are 5-digit strings).
        text_vals = (
            [_normalize_zip(v) for v in df[input_col].to_list()]
            if input_col and input_col in df.columns else [None] * df.height
        )
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
                "zip": "zip",
                "centroid_lat": "centroid_lat",
                "centroid_lon": "centroid_lon",
                "land_area_m2": "land_area_m2",
            },
        )
        result_df = df.with_columns([pl.Series(name, vals) for name, vals in out.items()])
        matched = sum(1 for i in indices if i is not None)
        return PolarsResult(
            output=result_df,
            artifacts=[{
                "kind": "lookup_summary",
                "label": "📮 US ZIP boundary lookup",
                "rows": df.height,
                "matched": matched,
                "unmatched": df.height - matched,
                "note": "Boundaries are equal-area circles around the gazetteer centroid — approximate.",
            }],
        )

    def infer_schema(self, input_schemas, params):
        s = dict(input_schemas.get("in", {}))
        out_col = params.get("output_column") or "zip_geometry"
        s[out_col] = "blob"
        s[f"{out_col}_zip"] = "string"
        s[f"{out_col}_centroid_lat"] = "double"
        s[f"{out_col}_centroid_lon"] = "double"
        s[f"{out_col}_land_area_m2"] = "double"
        return s


step = WkbByUsZipStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

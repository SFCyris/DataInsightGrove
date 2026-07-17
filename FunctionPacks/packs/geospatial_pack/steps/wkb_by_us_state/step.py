"""Boundary lookup: any US state identifier → WKB MULTIPOLYGON.

Accepts USPS 2-letter, FIPS 2-digit, full state name (case-insensitive),
or a lat/lon point. Output column carries raw WKB bytes plus a few
metadata companion columns; the consuming step (typically
export_to_map mode=choropleth) reads the geometry column directly.

Reference data: us_states_10m.parquet — US Census TIGER state outlines
at 1:10,000,000 scale, packaged by topojson/us-atlas v3 (public domain).
Decoded once per worker process; STRtree built for the point-input path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.extensions.pack_data import pack_data

# Import the shared helper. The pack's _lookup_common.py lives next to
# the steps/ tree, so we add the pack root to sys.path on first import.
_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))
from _lookup_common import load_reference, resolve_row, output_columns_for  # noqa: E402


_KEY_ORDER = ["usps", "fips", "name"]


def _get_dataset():
    path = pack_data("geospatial_pack", "us_states_10m")
    return load_reference(
        path,
        key_columns={"usps": "usps", "fips": "fips", "name": "name"},
    )


class WkbByUsStateStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        mode = params.get("input_mode") or "auto"
        out_col = params.get("output_column") or "state_geometry"
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
                "code": "usps",
                "fips": "fips",
                "centroid_lat": "centroid_lat",
                "centroid_lon": "centroid_lon",
            },
        )
        # Geometry is BLOB; metadata is mixed VARCHAR/DOUBLE. Polars
        # picks dtypes from the list contents automatically.
        result_df = df.with_columns([
            pl.Series(name, vals)
            for name, vals in out.items()
        ])
        matched = sum(1 for i in indices if i is not None)
        return PolarsResult(
            output=result_df,
            artifacts=[{
                "kind": "lookup_summary",
                "label": "🗺 US state boundary lookup",
                "rows": df.height,
                "matched": matched,
                "unmatched": df.height - matched,
            }],
        )

    def infer_schema(self, input_schemas, params):
        s = dict(input_schemas.get("in", {}))
        out_col = params.get("output_column") or "state_geometry"
        s[out_col] = "blob"
        s[f"{out_col}_name"] = "string"
        s[f"{out_col}_code"] = "string"
        s[f"{out_col}_fips"] = "string"
        s[f"{out_col}_centroid_lat"] = "double"
        s[f"{out_col}_centroid_lon"] = "double"
        return s


step = WkbByUsStateStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

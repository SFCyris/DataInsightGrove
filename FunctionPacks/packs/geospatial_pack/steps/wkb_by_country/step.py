"""Boundary lookup: any country (or supra-national aggregate) identifier
→ WKB MULTIPOLYGON.

Accepts:
  - ISO 3166 alpha-2 (``US``), alpha-3 (``USA``), numeric (``840``)
  - The country name (case-insensitive)
  - A lat/lon point
  - Aggregate codes: ``EU``, ``EEA``, ``Schengen``, ``G7``, ``G20``,
    ``BRICS``, ``USMCA``, ``ASEAN`` (and their full names / aliases)

When the same string could resolve to either a sovereign country or
an aggregate, the country wins. Aggregates are matched on their
dedicated code (``EU``), their full name (``European Union``), and
common aliases (``Europäische Union``, ``Union européenne``, …).

Resolution selection
--------------------
The bundled data ships at two resolutions:

  - **10m** — ~254 entities including microstates (Malta, Liechtenstein,
    Monaco, San Marino, Andorra, Singapore). 4.7 MB parquet.
  - **110m** — ~177 entities, microstates omitted. 130 KB parquet,
    fast to load and lean to render at world scale.

The ``resolution`` param picks one:

  - ``auto`` (default): we load 110m first to get centroids of matched
    rows, compute their bbox diagonal, and pick 10m when diagonal ≤ 60°
    (country/region scale) or 110m when > 60° (world scale).
  - ``country`` → force 10m.
  - ``world`` → force 110m.

The chosen resolution is reported in the lookup_summary artifact along
with the bbox diagonal so the user can verify the decision.
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
    load_reference,
    resolve_row_multi,
    output_columns_for_multi,
    _MultiDataset,
)


_COUNTRY_KEYS = ["alpha_2", "alpha_3", "numeric", "name"]
_AGGREGATE_KEYS = ["code", "aliases"]

# Auto-resolution threshold. Bbox diagonal of matched centroids (in
# degrees of lat+lon, Euclidean) above this → world scale → 110m.
# 60° is roughly "two continents wide" — at that scale microstate
# detail is invisible anyway, and the lean 130 KB load + smaller
# vertex count make world renders noticeably faster.
_WORLD_SCALE_DIAGONAL_DEG = 60.0


def _load_dataset(resolution: str) -> _MultiDataset:
    """Load (countries, aggregates) at the named resolution."""
    suffix = "10m" if resolution == "country" else "110m"
    countries = load_reference(
        pack_data("geospatial_pack", f"world_countries_{suffix}"),
        key_columns={
            "alpha_2": "alpha_2",
            "alpha_3": "alpha_3",
            "numeric": "numeric",
            "name": "name",
        },
    )
    aggregates = load_reference(
        pack_data("geospatial_pack", f"world_aggregates_{suffix}"),
        key_columns={"code": "code", "aliases": "aliases", "name": "name"},
        multi_value_columns=("aliases",),
    )
    return _MultiDataset(primary=countries, secondary=aggregates)


def _compute_bbox_diagonal(
    multi: _MultiDataset, hits: list[tuple[int, str] | None],
) -> float | None:
    """Bbox diagonal (in degrees) of matched centroids across both
    datasets. None if nothing matched."""
    pc_lat = multi.primary.df["centroid_lat"].to_list()
    pc_lon = multi.primary.df["centroid_lon"].to_list()
    sc_lat = multi.secondary.df["centroid_lat"].to_list()
    sc_lon = multi.secondary.df["centroid_lon"].to_list()
    lats: list[float] = []
    lons: list[float] = []
    for h in hits:
        if h is None:
            continue
        idx, child = h
        if child == "primary":
            lats.append(pc_lat[idx]); lons.append(pc_lon[idx])
        else:
            lats.append(sc_lat[idx]); lons.append(sc_lon[idx])
    if not lats:
        return None
    diag_lat = max(lats) - min(lats)
    diag_lon = max(lons) - min(lons)
    return (diag_lat ** 2 + diag_lon ** 2) ** 0.5


class WkbByCountryStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        mode = params.get("input_mode") or "auto"
        out_col = params.get("output_column") or "country_geometry"
        input_col = params.get("input_column")
        lat_col = params.get("lat_column")
        lon_col = params.get("lon_column")
        requested_resolution = (params.get("resolution") or "auto").lower()

        text_vals = df[input_col].to_list() if input_col and input_col in df.columns else [None] * df.height
        lat_vals = df[lat_col].to_list() if lat_col and lat_col in df.columns else [None] * df.height
        lon_vals = df[lon_col].to_list() if lon_col and lon_col in df.columns else [None] * df.height

        # Always resolve hits against 110m first — it's tiny + fast and
        # we need its centroids to decide auto-resolution anyway.
        coarse = _load_dataset("world")
        hits_coarse: list[tuple[int, str] | None] = [
            resolve_row_multi(
                coarse,
                input_mode=mode,
                text_value=text_vals[i],
                lat=lat_vals[i],
                lon=lon_vals[i],
                primary_key_order=_COUNTRY_KEYS,
                secondary_key_order=_AGGREGATE_KEYS,
            )
            for i in range(df.height)
        ]

        # Decide final resolution.
        bbox_diag_deg = _compute_bbox_diagonal(coarse, hits_coarse)
        if requested_resolution == "auto":
            if bbox_diag_deg is None:
                chosen = "world"
                reason = "no rows matched at 110m — defaulting to world"
            elif bbox_diag_deg > _WORLD_SCALE_DIAGONAL_DEG:
                chosen = "world"
                reason = (
                    f"bbox diagonal {bbox_diag_deg:.1f}° exceeds "
                    f"{_WORLD_SCALE_DIAGONAL_DEG:.0f}° threshold — using "
                    "110m (microstates surface as proxy dots in choropleth)"
                )
            else:
                chosen = "country"
                reason = (
                    f"bbox diagonal {bbox_diag_deg:.1f}° within "
                    f"{_WORLD_SCALE_DIAGONAL_DEG:.0f}° threshold — using "
                    "10m for country-scale detail"
                )
        else:
            chosen = requested_resolution
            reason = f"explicit override (resolution={requested_resolution})"

        # If we chose 10m, re-resolve against the high-detail dataset so
        # microstates that 110m missed get their real polygons. Otherwise
        # reuse hits_coarse (already correct against 110m).
        if chosen == "country":
            multi = _load_dataset("country")
            hits: list[tuple[int, str] | None] = [
                resolve_row_multi(
                    multi,
                    input_mode=mode,
                    text_value=text_vals[i],
                    lat=lat_vals[i],
                    lon=lon_vals[i],
                    primary_key_order=_COUNTRY_KEYS,
                    secondary_key_order=_AGGREGATE_KEYS,
                )
                for i in range(df.height)
            ]
        else:
            multi = coarse
            hits = hits_coarse

        out = output_columns_for_multi(
            multi, hits,
            output_column=out_col,
            metadata_columns={
                "name": "name",
                "alpha2": "alpha_2",
                "alpha3": "alpha_3",
                "code": "code",
                "centroid_lat": "centroid_lat",
                "centroid_lon": "centroid_lon",
            },
        )
        result_df = df.with_columns([pl.Series(name, vals) for name, vals in out.items()])
        matched = sum(1 for h in hits if h is not None)
        matched_aggregates = sum(1 for h in hits if h is not None and h[1] == "secondary")
        return PolarsResult(
            output=result_df,
            artifacts=[{
                "kind": "lookup_summary",
                "label": "🌍 Country boundary lookup",
                "rows": df.height,
                "matched": matched,
                "matched_aggregates": matched_aggregates,
                "unmatched": df.height - matched,
                "resolution_requested": requested_resolution,
                "resolution_chosen": chosen,
                "resolution_label": "1:10,000,000" if chosen == "country" else "1:110,000,000",
                "bbox_diagonal_deg": (
                    None if bbox_diag_deg is None else round(bbox_diag_deg, 2)
                ),
                "resolution_reason": reason,
            }],
        )

    def infer_schema(self, input_schemas, params):
        s = dict(input_schemas.get("in", {}))
        out_col = params.get("output_column") or "country_geometry"
        s[out_col] = "blob"
        s[f"{out_col}_name"] = "string"
        s[f"{out_col}_alpha2"] = "string"
        s[f"{out_col}_alpha3"] = "string"
        s[f"{out_col}_code"] = "string"
        s[f"{out_col}_centroid_lat"] = "double"
        s[f"{out_col}_centroid_lon"] = "double"
        return s


step = WkbByCountryStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

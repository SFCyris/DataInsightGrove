"""reverse_geocode — lat/lon → country/state via reverse_geocoder lookup.

Uses the `reverse_geocoder` library which bundles a ~3M-point KDTree of
populated places — no network, no API key, no external service. Returns
ISO-A2 country code, country name, and (when level = state) the
admin-1 subdivision name. For street-level reverse geocoding, a
geocoding service is required.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ReverseGeocodeStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        try:
            import reverse_geocoder as rg
        except ImportError as e:
            raise ImportError(
                "reverse_geocode requires `reverse_geocoder`. "
                "Install via the pack's pythonRequirements (auto on pack install)."
            ) from e

        df = inputs["in"]
        lat_col = params["latColumn"]; lon_col = params["lonColumn"]
        level = (params.get("level") or "country").lower()
        country_col = params.get("countryColumn") or "country"
        state_col = params.get("stateColumn") or "state"

        if lat_col not in df.columns:
            raise ValueError(f"reverse_geocode: latColumn {lat_col!r} not found")
        if lon_col not in df.columns:
            raise ValueError(f"reverse_geocode: lonColumn {lon_col!r} not found")

        lats = df[lat_col].to_list()
        lons = df[lon_col].to_list()
        # rg.search expects a list of (lat, lon) tuples.
        coords = [(la, lo) for la, lo in zip(lats, lons) if la is not None and lo is not None]
        # Build an index map from row → coords-position to handle nulls.
        idx_map: list[int | None] = []
        cursor = 0
        for la, lo in zip(lats, lons):
            if la is None or lo is None:
                idx_map.append(None)
            else:
                idx_map.append(cursor); cursor += 1
        results = rg.search(coords, mode=1) if coords else []

        countries: list[str | None] = []
        states: list[str | None] = []
        for idx in idx_map:
            if idx is None:
                countries.append(None); states.append(None)
                continue
            r = results[idx]
            countries.append(r.get("cc"))
            states.append(r.get("admin1"))

        new_cols = [pl.Series(country_col, countries)]
        if level == "state":
            new_cols.append(pl.Series(state_col, states))
        out_df = df.with_columns(new_cols)
        return PolarsResult(output=out_df)


step = ReverseGeocodeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

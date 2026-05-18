"""crs_transform — reproject coordinates between coordinate reference systems.

pyproj.Transformer is the workhorse: thread-safe, vectorised across
arrays, handles every EPSG code plus arbitrary PROJ strings. The
``always_xy=True`` flag normalises axis order so the user always
provides (lon, lat) regardless of what the underlying CRS prefers,
matching the convention every web mapping library uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class CrsTransformStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from pyproj import Transformer

        df = inputs["in"]
        x_col = params["xColumn"]
        y_col = params["yColumn"]
        src_crs = params.get("sourceCrs") or "EPSG:4326"
        tgt_crs = params.get("targetCrs") or "EPSG:3857"
        out_x = params.get("outputXColumn") or "x_proj"
        out_y = params.get("outputYColumn") or "y_proj"

        if x_col not in df.columns:
            raise ValueError(f"crs_transform: xColumn {x_col!r} not found")
        if y_col not in df.columns:
            raise ValueError(f"crs_transform: yColumn {y_col!r} not found")

        try:
            transformer = Transformer.from_crs(src_crs, tgt_crs, always_xy=True)
        except Exception as e:
            raise ValueError(
                f"crs_transform: could not build transformer from "
                f"{src_crs!r} to {tgt_crs!r}: {e}",
            ) from e

        xs = df[x_col].to_list()
        ys = df[y_col].to_list()

        # pyproj handles arrays directly; pass NULL-safe lists.
        # Replace None with NaN so the C bridge accepts them, then
        # restore None on output.
        import math
        xs_clean = [float(v) if v is not None else math.nan for v in xs]
        ys_clean = [float(v) if v is not None else math.nan for v in ys]
        x_out, y_out = transformer.transform(xs_clean, ys_clean)
        x_out_list = [None if (v is None or math.isnan(v)) else float(v) for v in x_out]
        y_out_list = [None if (v is None or math.isnan(v)) else float(v) for v in y_out]

        out_df = df.with_columns([
            pl.Series(out_x, x_out_list),
            pl.Series(out_y, y_out_list),
        ])
        return PolarsResult(output=out_df)


step = CrsTransformStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

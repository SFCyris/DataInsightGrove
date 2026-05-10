"""Convert coordinates between polar, Cartesian, and geographic systems.

Conversion catalog (`fromType` → `toType`):

  cartesian2d ↔ polar2d        — pure 2D trig, lossless
  cartesian3d ↔ polar3d        — pure 3D spherical, lossless (ISO physics
                                 convention: θ inclination, φ azimuth)
  cartesian3d ↔ geographic     — ECEF ↔ lat/lon on WGS84 ellipsoid
  polar  ↔ geographic          — routed through cartesian
  same  → same                 — copied (degenerate but allowed)

WGS84 ellipsoid constants are used for the geographic conversion (semi-major
axis a = 6,378,137 m; flattening f = 1/298.257223563). The forward conversion
ECEF→geodetic uses the closed-form Bowring approximation (good to ~µm).

This step is Polars-engine (not SQL) because the conversion involves trig
functions and conditional ellipsoid math that's cleaner in Python than as a
DuckDB CASE expression. The engine.browser="none" reflects that — preview
falls back to backend execution.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step

# ── WGS84 ellipsoid constants ────────────────────────────────────────
_WGS84_A = 6_378_137.0                 # semi-major axis (m)
_WGS84_F = 1.0 / 298.257_223_563       # flattening
_WGS84_B = _WGS84_A * (1 - _WGS84_F)   # semi-minor axis
_WGS84_E2 = (_WGS84_A**2 - _WGS84_B**2) / _WGS84_A**2  # first eccentricity²
_WGS84_EP2 = (_WGS84_A**2 - _WGS84_B**2) / _WGS84_B**2 # second eccentricity²


# ── Conversion primitives ────────────────────────────────────────────


def _polar2d_to_cartesian2d(r: float, theta: float) -> tuple[float, float]:
    """(r, θ) → (x, y). θ in radians."""
    return r * math.cos(theta), r * math.sin(theta)


def _cartesian2d_to_polar2d(x: float, y: float) -> tuple[float, float]:
    """(x, y) → (r, θ). θ in [-π, π]."""
    return math.hypot(x, y), math.atan2(y, x)


def _polar3d_to_cartesian3d(r: float, theta: float, phi: float) -> tuple[float, float, float]:
    """Spherical (r, θ inclination, φ azimuth) → (x, y, z). θ ∈ [0, π], φ ∈ [-π, π]."""
    sin_t = math.sin(theta)
    return (
        r * sin_t * math.cos(phi),
        r * sin_t * math.sin(phi),
        r * math.cos(theta),
    )


def _cartesian3d_to_polar3d(x: float, y: float, z: float) -> tuple[float, float, float]:
    """(x, y, z) → spherical (r, θ inclination, φ azimuth)."""
    r = math.sqrt(x * x + y * y + z * z)
    if r == 0.0:
        return 0.0, 0.0, 0.0
    return r, math.acos(z / r), math.atan2(y, x)


def _geographic_to_cartesian3d(lat_deg: float, lon_deg: float, h: float = 0.0) -> tuple[float, float, float]:
    """WGS84 lat/lon (degrees) + ellipsoidal height (m) → ECEF (x, y, z) in m."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    n = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
    return (
        (n + h) * cos_lat * math.cos(lon),
        (n + h) * cos_lat * math.sin(lon),
        (n * (1.0 - _WGS84_E2) + h) * sin_lat,
    )


def _cartesian3d_to_geographic(x: float, y: float, z: float) -> tuple[float, float]:
    """ECEF (x, y, z) → WGS84 (lat, lon) in degrees. Drops ellipsoidal height.

    Bowring's closed-form approximation. Accurate to ~µm for terrestrial
    points; iterative refinement available in pyproj if sub-µm needed.
    """
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    if p == 0.0:
        return (90.0 if z >= 0 else -90.0), math.degrees(lon)
    theta = math.atan2(z * _WGS84_A, p * _WGS84_B)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    lat = math.atan2(
        z + _WGS84_EP2 * _WGS84_B * sin_t**3,
        p - _WGS84_E2 * _WGS84_A * cos_t**3,
    )
    return math.degrees(lat), math.degrees(lon)


# ── Output column naming per target system ───────────────────────────

_TARGET_COLUMNS: dict[str, list[str]] = {
    "cartesian2d": ["x", "y"],
    "cartesian3d": ["x", "y", "z"],
    "polar2d":     ["r", "theta"],
    "polar3d":     ["r", "theta", "phi"],
    "geographic":  ["lat", "lon"],
}

_SOURCE_DIM: dict[str, int] = {
    "cartesian2d": 2,
    "cartesian3d": 3,
    "polar2d":     2,
    "polar3d":     3,
    "geographic":  2,  # lat, lon (height optional, defaults to 0)
}


def _convert_one(
    from_type: str, to_type: str, vals: tuple[float, ...],
) -> tuple[float, ...]:
    """Single-row conversion. Routes via cartesian when needed."""
    if from_type == to_type:
        return vals

    # Lift source into cartesian first, then drop into target.
    if from_type == "cartesian2d":
        x, y = vals
        if to_type == "polar2d":
            return _cartesian2d_to_polar2d(x, y)
        if to_type == "cartesian3d":
            return (x, y, 0.0)
        if to_type == "polar3d":
            return _cartesian3d_to_polar3d(x, y, 0.0)
        if to_type == "geographic":
            return _cartesian3d_to_geographic(x, y, 0.0)

    if from_type == "cartesian3d":
        x, y, z = vals
        if to_type == "polar3d":
            return _cartesian3d_to_polar3d(x, y, z)
        if to_type == "cartesian2d":
            return (x, y)
        if to_type == "polar2d":
            return _cartesian2d_to_polar2d(x, y)
        if to_type == "geographic":
            return _cartesian3d_to_geographic(x, y, z)

    if from_type == "polar2d":
        r, theta = vals
        cart = _polar2d_to_cartesian2d(r, theta)
        return _convert_one("cartesian2d", to_type, cart)

    if from_type == "polar3d":
        r, theta, phi = vals
        cart = _polar3d_to_cartesian3d(r, theta, phi)
        return _convert_one("cartesian3d", to_type, cart)

    if from_type == "geographic":
        lat, lon = vals
        cart = _geographic_to_cartesian3d(lat, lon)
        return _convert_one("cartesian3d", to_type, cart)

    raise ValueError(f"Unknown fromType: {from_type!r}")


# ── Step implementation ──────────────────────────────────────────────


class ConvertCoordinatesStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        from_type = params["fromType"]
        to_type = params["toType"]
        source_cols = params["sourceColumns"]
        prefix = params.get("outputPrefix", "coord_")

        expected_dim = _SOURCE_DIM[from_type]
        if len(source_cols) != expected_dim:
            raise ValueError(
                f"convert_coordinates: {from_type} requires {expected_dim} source "
                f"columns, got {len(source_cols)}",
            )

        target_cols = [f"{prefix}{name}" for name in _TARGET_COLUMNS[to_type]]

        # Vectorize: pull source columns into NumPy arrays via Polars, run
        # row-wise conversion. For typical UI-preview sample sizes (≤200k
        # rows) this is fine; large-scale runs could be vectorized with
        # NumPy expressions but would lose readability.
        src_rows = df.select(source_cols).to_numpy()
        out: list[list[float]] = []
        for row in src_rows:
            try:
                converted = _convert_one(from_type, to_type, tuple(float(v) for v in row))
                out.append(list(converted))
            except (TypeError, ValueError):
                out.append([float("nan")] * len(target_cols))

        out_df = df.clone()
        for i, col_name in enumerate(target_cols):
            out_df = out_df.with_columns(
                pl.Series(col_name, [r[i] for r in out], dtype=pl.Float64),
            )
        return PolarsResult(output=out_df)

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        to_type = params.get("toType")
        prefix = params.get("outputPrefix", "coord_")
        if to_type and to_type in _TARGET_COLUMNS:
            for c in _TARGET_COLUMNS[to_type]:
                s[f"{prefix}{c}"] = "double"
        return s


step = ConvertCoordinatesStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

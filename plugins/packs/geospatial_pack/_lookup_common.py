"""Shared helpers for the boundary-lookup steps.

Each ``wkb_by_*`` step in this pack follows the same pattern:

  1. The step has either a ``input_column`` (textual: code/name/zip) or
     ``lat_column`` + ``lon_column`` (geospatial point).
  2. The step reads its reference dataset once via pack_data() with a
     module-level cache so the parquet decodes once per worker process.
  3. The step builds an STRtree over the geometries for fast
     point-in-polygon, also cached.
  4. The step calls ``lookup_by_value`` (text path) or
     ``lookup_by_point`` (spatial path) per row.

This module centralises those routines so each step file is small.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


@dataclass
class _RefDataset:
    """Cached in-memory view of a boundary parquet.

    Attributes
    ----------
    df          : the full DataFrame
    geometries  : list[shapely.geometry] in row order (decoded from WKB)
    tree        : shapely.strtree.STRtree over geometries
    by_key      : dict[str, int] — lookup-key → row index. The step
                  provides the key-extractor; typically multiple lookup
                  modes share one dataset (state-by-USPS, state-by-name,
                  state-by-FIPS all read the same parquet).
    """
    df: pl.DataFrame
    geometries: list[Any]
    tree: Any
    by_key: dict[str, dict[str, int]]


_DATASETS: dict[Path, _RefDataset] = {}
_DATASET_LOCK = threading.Lock()


def load_reference(
    path: Path,
    key_columns: dict[str, str],
    *,
    multi_value_columns: tuple[str, ...] = (),
) -> _RefDataset:
    """Lazy-load a boundary parquet + build indexes.

    Parameters
    ----------
    path : the parquet path returned by ``pack_data(pack_id, resource_id)``
    key_columns : ``{key_name: column_name}`` — each key_name registers
        a lookup table; the column values are normalised (uppercased +
        stripped) for case-insensitive matching.
    multi_value_columns : names of key_columns whose source values are
        pipe-separated lists of aliases (e.g. an ``aliases`` column with
        ``"European Union|Européische Union|Union européenne"``). Each
        alias becomes its own entry in the index pointing at the same
        row. Use for alternate names per row.

    Returns a cached ``_RefDataset``; subsequent calls with the same
    ``path`` return the same object (the ``key_columns`` of the first
    call wins — pass the superset).
    """
    if path in _DATASETS:
        return _DATASETS[path]
    with _DATASET_LOCK:
        if path in _DATASETS:
            return _DATASETS[path]
        from shapely import wkb
        from shapely.strtree import STRtree
        df = pl.read_parquet(path)
        # Decode every WKB row → Shapely geometry. ~50ms for 50 states,
        # ~500ms for 200 countries, ~30s for 30k ZCTAs. Done once.
        geoms = [wkb.loads(b) for b in df["geometry_wkb"].to_list()]
        tree = STRtree(geoms)
        # Build keyed indexes.
        by_key: dict[str, dict[str, int]] = {}
        for key_name, col_name in key_columns.items():
            if col_name not in df.columns:
                continue
            idx: dict[str, int] = {}
            for i, val in enumerate(df[col_name].to_list()):
                if val is None or val == "":
                    continue
                if key_name in multi_value_columns:
                    # Split on pipe; index each alias separately so any
                    # of them resolves to the same row.
                    for piece in str(val).split("|"):
                        piece_clean = piece.strip().upper()
                        if piece_clean:
                            idx[piece_clean] = i
                else:
                    idx[str(val).strip().upper()] = i
            by_key[key_name] = idx
        ds = _RefDataset(df=df, geometries=geoms, tree=tree, by_key=by_key)
        _DATASETS[path] = ds
        return ds


def lookup_by_value(
    dataset: _RefDataset,
    value: Any,
    *,
    key_order: list[str],
) -> int | None:
    """Find a row index by trying each registered key in order.

    ``key_order`` is the precedence list — e.g. for US states:
    ``["usps", "fips", "name"]`` means "try USPS first, then FIPS, then
    full name". Each key's index was pre-built with uppercased values,
    so the caller doesn't need to know the case-normalisation rule.
    """
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    for k in key_order:
        idx = dataset.by_key.get(k)
        if idx is None:
            continue
        hit = idx.get(s)
        if hit is not None:
            return hit
    return None


def lookup_by_point(dataset: _RefDataset, lat: float, lon: float) -> int | None:
    """Point-in-polygon via STRtree. Returns the row index of the
    first containing geometry, or None if no polygon contains the point.
    """
    if lat is None or lon is None:
        return None
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None
    from shapely.geometry import Point
    p = Point(lon_f, lat_f)
    # STRtree.query returns candidate indices whose bounding boxes
    # contain the point. We still need a fine-grained .contains check.
    candidates = dataset.tree.query(p)
    for i in candidates:
        if dataset.geometries[i].contains(p):
            return int(i)
    return None


def resolve_row(
    dataset: _RefDataset,
    *,
    input_mode: str,
    text_value: Any = None,
    lat: Any = None,
    lon: Any = None,
    key_order: list[str],
) -> int | None:
    """Auto-detect dispatcher used by every lookup step.

    ``input_mode`` is one of: ``"text"``, ``"point"``, ``"auto"``.
    In auto mode the function tries text first (cheaper), falls back
    to point lookup.
    """
    if input_mode == "text":
        return lookup_by_value(dataset, text_value, key_order=key_order)
    if input_mode == "point":
        return lookup_by_point(dataset, lat, lon)
    # auto
    if text_value is not None:
        hit = lookup_by_value(dataset, text_value, key_order=key_order)
        if hit is not None:
            return hit
    if lat is not None and lon is not None:
        return lookup_by_point(dataset, lat, lon)
    return None


@dataclass
class _MultiDataset:
    """Composite lookup over two parquet datasets that share a common
    output schema. Used by ``wkb_by_country`` to chain
    sovereign-countries first, then the world_aggregates parquet
    (EU / EEA / G7 / …) so the same lookup column accepts both
    "DE" and "EU".

    Both child datasets MUST contain a ``geometry_wkb`` column.
    Metadata column extraction reads from the matching child for each
    resolved row — the caller passes a single ``metadata_columns``
    mapping per OUTPUT suffix; for each child we resolve to that
    column if present, else None.
    """
    primary: _RefDataset
    secondary: _RefDataset


def resolve_row_multi(
    multi: _MultiDataset,
    *,
    input_mode: str,
    text_value: Any = None,
    lat: Any = None,
    lon: Any = None,
    primary_key_order: list[str],
    secondary_key_order: list[str],
) -> tuple[int, str] | None:
    """Try the primary dataset's keys first; fall back to the secondary.

    Returns ``(row_index, 'primary' | 'secondary')`` or None when nothing
    matched. Point-input also tries primary then secondary.
    """
    if input_mode in ("text", "auto") and text_value is not None:
        idx = lookup_by_value(multi.primary, text_value, key_order=primary_key_order)
        if idx is not None:
            return (idx, "primary")
        idx = lookup_by_value(multi.secondary, text_value, key_order=secondary_key_order)
        if idx is not None:
            return (idx, "secondary")
    if input_mode in ("point", "auto") and lat is not None and lon is not None:
        idx = lookup_by_point(multi.primary, lat, lon)
        if idx is not None:
            return (idx, "primary")
        idx = lookup_by_point(multi.secondary, lat, lon)
        if idx is not None:
            return (idx, "secondary")
    return None


def output_columns_for_multi(
    multi: _MultiDataset,
    hits: list[tuple[int, str] | None],
    *,
    output_column: str,
    metadata_columns: dict[str, str],
) -> dict[str, list]:
    """Build output columns from mixed primary/secondary row references.

    For each hit, reads geometry_wkb from the matching child dataset.
    Metadata columns are resolved per child — if a child lacks the
    source column for a given suffix, that row gets None.
    """
    n = len(hits)
    wkb_col: list[bytes | None] = [None] * n
    meta_cols: dict[str, list] = {f"{output_column}_{suffix}": [None] * n for suffix in metadata_columns}

    primary_wkb = multi.primary.df["geometry_wkb"].to_list()
    secondary_wkb = multi.secondary.df["geometry_wkb"].to_list()
    primary_sources: dict[str, list] = {
        suffix: multi.primary.df[col].to_list() if col in multi.primary.df.columns else None
        for suffix, col in metadata_columns.items()
    }
    secondary_sources: dict[str, list] = {
        suffix: multi.secondary.df[col].to_list() if col in multi.secondary.df.columns else None
        for suffix, col in metadata_columns.items()
    }

    for row, hit in enumerate(hits):
        if hit is None:
            continue
        idx, child = hit
        if child == "primary":
            wkb_col[row] = primary_wkb[idx]
            for suffix in metadata_columns:
                src = primary_sources[suffix]
                if src is not None:
                    meta_cols[f"{output_column}_{suffix}"][row] = src[idx]
        else:
            wkb_col[row] = secondary_wkb[idx]
            for suffix in metadata_columns:
                src = secondary_sources[suffix]
                if src is not None:
                    meta_cols[f"{output_column}_{suffix}"][row] = src[idx]
    return {output_column: wkb_col, **meta_cols}


def output_columns_for(
    df: pl.DataFrame,
    indices: list[int | None],
    *,
    output_column: str,
    metadata_columns: dict[str, str],
) -> dict[str, list]:
    """Build the output column vectors from a list of resolved row indices.

    ``metadata_columns`` maps ``output_suffix → source_column`` —
    e.g. ``{"name": "name", "code": "usps", "centroid_lat": "centroid_lat"}``
    becomes columns ``{output_column}_name``, ``{output_column}_code``,
    ``{output_column}_centroid_lat`` in the output frame.

    The geometry itself is always emitted at ``{output_column}`` as raw
    WKB bytes.
    """
    n = len(indices)
    wkb_col: list[bytes | None] = [None] * n
    meta_cols: dict[str, list] = {f"{output_column}_{suffix}": [None] * n for suffix in metadata_columns}
    wkb_source = df["geometry_wkb"].to_list()
    source_lists = {suffix: df[col].to_list() for suffix, col in metadata_columns.items()}
    for row, idx in enumerate(indices):
        if idx is None:
            continue
        wkb_col[row] = wkb_source[idx]
        for suffix in metadata_columns:
            meta_cols[f"{output_column}_{suffix}"][row] = source_lists[suffix][idx]
    return {output_column: wkb_col, **meta_cols}

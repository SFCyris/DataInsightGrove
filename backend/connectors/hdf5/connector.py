"""HDF5 connector — picks a single tabular dataset out of a (possibly
hierarchical) HDF5 file and returns it as a polars LazyFrame.

Selection rule for 'path' = unset:
  walk the tree depth-first, return the first 2-D Dataset.
  Fall back to the first Dataset of any rank.
  Compound dtypes (HDF5's named-field equivalent of numpy structured arrays)
  also count as tabular at any rank.

Multi-dataset HDF5 files are common in scientific work; if the heuristic
guesses wrong the user can set `path` explicitly. A future change can
surface a picker UI similar to Excel's sheet picker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


def _path(uri: str) -> Path:
    if uri.startswith("file://"):
        return Path(urlparse(uri).path)
    return Path(uri)


def _walk_datasets(group: Any) -> list[tuple[str, Any]]:
    """Depth-first list of (path, dataset) tuples under `group`. Caller is
    expected to be inside the `with h5py.File(...) as f:` block."""
    out: list[tuple[str, Any]] = []

    def visit(name: str, obj: Any) -> None:
        # h5py marks datasets by absence of `.keys()`; check via type name to
        # avoid importing the class at module load time.
        if type(obj).__name__ == "Dataset":
            out.append((name, obj))

    group.visititems(visit)
    return out


def _pick_dataset(datasets: list[tuple[str, Any]], requested: str | None) -> tuple[str, Any]:
    if not datasets:
        raise ValueError("HDF5 file contains no datasets")
    if requested:
        # h5py's visititems strips the leading slash; normalise both sides.
        norm_req = requested.lstrip("/")
        for name, ds in datasets:
            if name == norm_req:
                return name, ds
        avail = ", ".join(f"/{n}" for n, _ in datasets[:10])
        more = "" if len(datasets) <= 10 else f" (+{len(datasets) - 10} more)"
        raise ValueError(f"HDF5 dataset '{requested}' not found. Available: {avail}{more}")
    # Prefer 2-D datasets.
    for name, ds in datasets:
        if ds.ndim == 2:
            return name, ds
    # Or any structured/compound dataset.
    for name, ds in datasets:
        if ds.dtype.names:
            return name, ds
    return datasets[0]


def _dataset_to_frame(name: str, ds: Any) -> pl.DataFrame:
    arr = ds[...]  # materialise the whole dataset to memory
    # Compound dtype → one column per field.
    if arr.dtype.names:
        return pl.DataFrame({fname: arr[fname].ravel() for fname in arr.dtype.names})
    if arr.ndim == 1:
        return pl.DataFrame({Path(name).name or "col_1": arr})
    if arr.ndim == 2:
        return pl.DataFrame({f"col_{i + 1}": arr[:, i] for i in range(arr.shape[1])})
    raise ValueError(
        f"HDF5 dataset '{name}' has shape {arr.shape} — only 1-D, 2-D, and "
        f"compound-dtype datasets are tabular. Pick a different path or "
        f"reshape upstream."
    )


class Hdf5Connector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        try:
            import h5py
        except ImportError as e:
            raise RuntimeError(
                "h5py is required to read HDF5 files. Install with "
                "`pip install dig[science]`."
            ) from e

        path = _path(uri)
        with h5py.File(path, "r") as f:
            datasets = _walk_datasets(f)
            name, ds = _pick_dataset(datasets, options.get("path"))
            df = _dataset_to_frame(name, ds)
        return df.lazy()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = Hdf5Connector(json.loads(_manifest_path.read_text()))

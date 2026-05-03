"""NumPy connector — reads .npy (single array) and .npz (zip of arrays)
into a polars LazyFrame.

Shape handling:
  - 1-D array          → single column (col_1 or the structured-dtype name)
  - 2-D array          → one column per second-axis index (col_1 … col_N)
  - structured dtype   → one column per field name (works at any rank)
  - 3+-D plain array   → rejected with an error suggesting reshape

For .npz with multiple arrays, the `name` option selects which one. Default
picks the first 2-D plain array, falling back to the first array overall."""

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


def _array_to_frame(arr: Any, hint_name: str | None = None) -> pl.DataFrame:
    import numpy as np  # local import: numpy ships with polars/pyarrow

    # Structured dtype → one column per field, regardless of rank.
    if arr.dtype.names:
        return pl.DataFrame({name: arr[name].ravel() for name in arr.dtype.names})

    if arr.ndim == 1:
        col = hint_name or "col_1"
        return pl.DataFrame({col: arr})
    if arr.ndim == 2:
        return pl.DataFrame(
            {f"col_{i + 1}": arr[:, i] for i in range(arr.shape[1])}
        )
    raise ValueError(
        f"NumPy array has shape {arr.shape} — only 1-D, 2-D, and structured "
        f"dtypes are tabular. Reshape to 2-D first or use a derived step."
    )


def _pick_npz_array(npz: Any, requested: str | None) -> tuple[str, Any]:
    """Return (name, array). If a name is requested, use it; else prefer the
    first 2-D plain array, then fall back to the first array overall."""
    names = list(npz.files)
    if not names:
        raise ValueError("npz archive is empty")
    if requested:
        if requested not in names:
            raise ValueError(
                f"npz has no array '{requested}'. Available: {', '.join(names)}"
            )
        return requested, npz[requested]
    for n in names:
        a = npz[n]
        if a.ndim == 2 and not a.dtype.names:
            return n, a
    return names[0], npz[names[0]]


class NumpyConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        try:
            import numpy as np
        except ImportError as e:
            raise RuntimeError(
                "numpy is required to read .npy / .npz files. It ships with "
                "the [engine] extra — install with `pip install dig[engine]`."
            ) from e

        path = _path(uri)
        ext = path.suffix.lower()
        if ext == ".npy":
            arr = np.load(path, allow_pickle=False)
            return _array_to_frame(arr).lazy()
        if ext == ".npz":
            with np.load(path, allow_pickle=False) as npz:
                name, arr = _pick_npz_array(npz, options.get("name"))
            return _array_to_frame(arr, hint_name=name).lazy()
        raise ValueError(f"numpy connector: unsupported extension '{ext}'")


_manifest_path = Path(__file__).parent / "manifest.json"
connector = NumpyConnector(json.loads(_manifest_path.read_text()))

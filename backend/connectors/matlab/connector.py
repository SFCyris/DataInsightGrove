"""MATLAB .mat connector.

Two file format families:
  - v4 / v6 / v7         : binary MAT, read via scipy.io.loadmat
  - v7.3+                : HDF5 under the hood, read via h5py

We try scipy first because it produces a clean dict of numpy arrays for the
common case. If scipy raises NotImplementedError (its signal for v7.3) or
ValueError on the file header, we fall back to h5py."""

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


def _array_to_frame(name: str, arr: Any) -> pl.DataFrame:
    if arr.dtype.names:
        return pl.DataFrame({fname: arr[fname].ravel() for fname in arr.dtype.names})
    if arr.ndim == 1:
        return pl.DataFrame({name: arr})
    if arr.ndim == 2:
        return pl.DataFrame({f"col_{i + 1}": arr[:, i] for i in range(arr.shape[1])})
    raise ValueError(
        f"MATLAB variable '{name}' has shape {arr.shape} — only 1-D, 2-D, "
        f"and struct variables are tabular. Pick a different variable."
    )


def _pick_scipy(vars_: dict[str, Any], requested: str | None) -> tuple[str, Any]:
    """Skip scipy's metadata keys (start with '__'). Pick by name or by the
    first 2-D numeric matrix."""
    import numpy as np

    candidates = {k: v for k, v in vars_.items() if not k.startswith("__")}
    if not candidates:
        raise ValueError("MAT file contains no user variables")
    if requested:
        if requested not in candidates:
            raise ValueError(
                f"MAT file has no variable '{requested}'. "
                f"Available: {', '.join(candidates.keys())}"
            )
        return requested, candidates[requested]
    for name, arr in candidates.items():
        if isinstance(arr, np.ndarray) and arr.ndim == 2 and not arr.dtype.names:
            return name, arr
    name, arr = next(iter(candidates.items()))
    return name, arr


def _read_via_h5py(path: Path, requested: str | None) -> pl.DataFrame:
    """v7.3+ MAT files. h5py exposes them as a normal HDF5 file with a
    `#refs#` group plus one entry per top-level MATLAB variable."""
    import h5py
    import numpy as np

    with h5py.File(path, "r") as f:
        names = [k for k in f.keys() if not k.startswith("#")]
        if not names:
            raise ValueError("MAT v7.3 file contains no top-level variables")
        target = requested or next(
            (n for n in names if type(f[n]).__name__ == "Dataset" and f[n].ndim == 2),
            names[0],
        )
        if target not in f:
            raise ValueError(
                f"MAT file has no variable '{target}'. Available: {', '.join(names)}"
            )
        node = f[target]
        if type(node).__name__ != "Dataset":
            raise ValueError(
                f"MAT variable '{target}' is a group, not a dataset. "
                f"Pick a leaf variable explicitly."
            )
        # MATLAB stores arrays in column-major order; h5py reads them as
        # row-major, so the shape comes out transposed. Transpose back.
        arr = np.asarray(node[...]).T
    return _array_to_frame(target, arr)


class MatlabConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        path = _path(uri)
        requested = options.get("name")

        try:
            from scipy import io as _scipy_io  # noqa: F401
        except ImportError:
            _scipy_io = None  # type: ignore[assignment]

        # Try scipy first (handles MAT v4–v7).
        if _scipy_io is not None:
            try:
                vars_ = _scipy_io.loadmat(path, squeeze_me=False, struct_as_record=False)
                name, arr = _pick_scipy(vars_, requested)
                return _array_to_frame(name, arr).lazy()
            except NotImplementedError:
                # scipy's signal for "use h5py for v7.3" — fall through.
                pass
            except ValueError:
                # Bad header / not a v4–7 MAT — try h5py.
                pass

        try:
            import h5py  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "Reading this .mat file needs either scipy (v4–v7) or h5py "
                "(v7.3+). Install both with `pip install dig[science]`."
            ) from e

        return _read_via_h5py(path, requested).lazy()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = MatlabConnector(json.loads(_manifest_path.read_text()))

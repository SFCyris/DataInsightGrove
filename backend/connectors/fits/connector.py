"""FITS connector — astronomy file format with a list of HDUs (Header-Data
Units). Reads via astropy.io.fits.

HDU selection rule when 'hdu' is unset:
  prefer the first BinTableHDU / TableHDU (column-oriented data),
  else the first ImageHDU with a 2-D image (rows × cols),
  else error with the HDU summary so the user can pick by index."""

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


def _table_hdu_to_frame(hdu: Any) -> pl.DataFrame:
    """astropy.io.fits.BinTableHDU.data is a record array — one column per
    field. Multi-element fields (vectors per row) get stringified to keep
    the schema rectangular."""
    data = hdu.data
    cols: dict[str, Any] = {}
    for name in data.dtype.names:
        col = data[name]
        if col.ndim == 1:
            cols[name] = col
        else:
            # Vector / multi-D field — flatten each row to a string so the
            # column stays rectangular. Users who actually need the array
            # can use a separate FITS-specific reader for now.
            cols[name] = [str(row.tolist()) for row in col]
    return pl.DataFrame(cols)


def _image_hdu_to_frame(hdu: Any) -> pl.DataFrame:
    arr = hdu.data
    if arr is None:
        raise ValueError("Image HDU has no data")
    if arr.ndim != 2:
        raise ValueError(
            f"Image HDU has shape {arr.shape}; only 2-D images are tabular. "
            f"Pick a different HDU via the 'hdu' option."
        )
    return pl.DataFrame({f"col_{i + 1}": arr[:, i] for i in range(arr.shape[1])})


def _summarise_hdus(hdul: Any) -> str:
    """Compact HDU listing for error messages: '0=Primary(image,2D 100x200) 1=BinTable(rows=512)'."""
    parts: list[str] = []
    for i, hdu in enumerate(hdul):
        kind = type(hdu).__name__
        if hasattr(hdu, "columns") and hdu.columns is not None:
            n = hdu.data.shape[0] if hdu.data is not None else 0
            parts.append(f"{i}={kind}(rows={n})")
        elif hdu.data is not None:
            parts.append(f"{i}={kind}(image,{hdu.data.ndim}D {hdu.data.shape})")
        else:
            parts.append(f"{i}={kind}(empty)")
    return " ".join(parts)


def _pick_hdu(hdul: Any) -> int:
    # Prefer table HDUs (BinTableHDU, TableHDU).
    for i, hdu in enumerate(hdul):
        if type(hdu).__name__ in ("BinTableHDU", "TableHDU"):
            return i
    # Else first 2-D image.
    for i, hdu in enumerate(hdul):
        if hdu.data is not None and getattr(hdu.data, "ndim", 0) == 2:
            return i
    raise ValueError(
        f"FITS file has no table HDUs or 2-D image HDUs. HDUs: {_summarise_hdus(hdul)}"
    )


class FitsConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        try:
            from astropy.io import fits as _fits
        except ImportError as e:
            raise RuntimeError(
                "astropy is required to read FITS files. Install with "
                "`pip install dig[science]`."
            ) from e

        path = _path(uri)
        with _fits.open(path, memmap=True) as hdul:
            requested = options.get("hdu")
            if requested is not None:
                idx = int(requested)
                if idx < 0 or idx >= len(hdul):
                    raise ValueError(
                        f"FITS HDU index {idx} out of range. "
                        f"HDUs: {_summarise_hdus(hdul)}"
                    )
            else:
                idx = _pick_hdu(hdul)
            hdu = hdul[idx]
            if type(hdu).__name__ in ("BinTableHDU", "TableHDU"):
                df = _table_hdu_to_frame(hdu)
            else:
                df = _image_hdu_to_frame(hdu)
        return df.lazy()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = FitsConnector(json.loads(_manifest_path.read_text()))

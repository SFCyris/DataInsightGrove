"""NetCDF connector — flattens a single data variable to a tabular long
form: one row per cell, columns = (coord_1, …, coord_N, value).

NetCDF files often hold multiple variables sharing the same coordinate
grid (e.g. temperature + pressure on lat × lon × time). The `variable`
option picks which one — default is the first data variable found. A
future change can offer a multi-variable wide-table mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


def _path(uri: str) -> Path:
    # Reject file:// URIs that escape the data dir / samples dir.
    # See dig.engine.uri_safety for the full rationale (round-2
    # pen-tester finding: arbitrary local file read via file:// URI).
    from dig.engine.uri_safety import assert_local_path_safe
    return assert_local_path_safe(uri)


class NetcdfConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        try:
            import xarray as xr
        except ImportError as e:
            raise RuntimeError(
                "xarray (and netCDF4) are required to read NetCDF files. "
                "Install with `pip install dig[science]`."
            ) from e

        path = _path(uri)
        ds = xr.open_dataset(path)
        try:
            data_vars = list(ds.data_vars.keys())
            if not data_vars:
                raise ValueError("NetCDF file contains no data variables")
            requested = options.get("variable")
            if requested:
                if requested not in data_vars:
                    raise ValueError(
                        f"NetCDF has no variable '{requested}'. "
                        f"Available: {', '.join(data_vars)}"
                    )
                vname = requested
            else:
                vname = data_vars[0]
            # to_dataframe stacks the N-D array into long form. reset_index
            # promotes coordinate dims from the index back into columns so
            # downstream pipeline steps see them as ordinary columns.
            df_pd = ds[vname].to_dataframe().reset_index()
        finally:
            ds.close()

        # pl.from_pandas handles datetime + string coercion for us.
        return pl.from_pandas(df_pd).lazy()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = NetcdfConnector(json.loads(_manifest_path.read_text()))

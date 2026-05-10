from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


class ParquetConnector(Connector):
    def _path(self, uri: str) -> Path:
        # Reject file:// URIs that escape the data dir / samples dir.
        # See dig.engine.uri_safety for the full rationale (round-2
        # pen-tester finding: arbitrary local file read).
        from dig.engine.uri_safety import assert_local_path_safe
        return assert_local_path_safe(uri)

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        return pl.scan_parquet(self._path(uri))

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = self._path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        comp = options.get("compression", "zstd")
        frame.write_parquet(path, compression="uncompressed" if comp == "uncompressed" else comp)


_manifest_path = Path(__file__).parent / "manifest.json"
connector = ParquetConnector(json.loads(_manifest_path.read_text()))

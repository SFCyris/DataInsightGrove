"""Apache Arrow IPC (Feather v2) connector. Polars has native readers; no
extra dependency beyond what the engine extra already pulls in (pyarrow)."""

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


class FeatherConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        return pl.scan_ipc(_path(uri))

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = _path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        comp = options.get("compression", "zstd")
        # polars takes None for uncompressed.
        frame.write_ipc(path, compression=None if comp == "uncompressed" else comp)


_manifest_path = Path(__file__).parent / "manifest.json"
connector = FeatherConnector(json.loads(_manifest_path.read_text()))

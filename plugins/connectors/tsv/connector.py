"""TSV (tab-separated values) connector.

Worked example from docs/AUTHORING_GUIDE.md (Tutorial 3). Wraps Polars's CSV
reader/writer with the delimiter pinned to '\\t'.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


class TsvConnector(Connector):
    def _path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            return Path(urlparse(uri).path)
        return Path(uri)

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        return pl.scan_csv(
            self._path(uri),
            separator="\t",
            has_header=options.get("header", True),
            encoding=options.get("encoding", "utf8"),
            infer_schema_length=10_000,
            try_parse_dates=True,
            ignore_errors=False,
        )

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = self._path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_csv(
            path,
            separator="\t",
            include_header=options.get("header", True),
        )


_manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
connector = TsvConnector(_manifest)

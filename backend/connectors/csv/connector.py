from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


class CsvConnector(Connector):
    def _path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            return Path(urlparse(uri).path)
        return Path(uri)

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        path = self._path(uri)
        delimiter = options.get("delimiter", ",")
        if delimiter == "\\t":
            delimiter = "\t"
        return pl.scan_csv(
            path,
            separator=delimiter,
            has_header=options.get("header", True),
            encoding=options.get("encoding", "utf8"),
            null_values=options.get("nullValues") or None,
            infer_schema_length=10_000,
            try_parse_dates=True,
            ignore_errors=False,
        )

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = self._path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        delimiter = options.get("delimiter", ",")
        if delimiter == "\\t":
            delimiter = "\t"
        frame.write_csv(
            path,
            separator=delimiter,
            include_header=options.get("header", True),
        )


_manifest_path = Path(__file__).parent / "manifest.json"
connector = CsvConnector(json.loads(_manifest_path.read_text()))

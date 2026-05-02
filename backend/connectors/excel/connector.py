from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


class ExcelConnector(Connector):
    def _path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            return Path(urlparse(uri).path)
        return Path(uri)

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        path = self._path(uri)
        sheet = options.get("sheet")
        # Polars routes to fastexcel or openpyxl depending on which is installed.
        df = pl.read_excel(
            path,
            sheet_name=sheet,
            engine="openpyxl",
            has_header=options.get("header", True),
        )
        return df.lazy()

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = self._path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet = options.get("sheet") or "Sheet1"
        frame.write_excel(path, worksheet=sheet)


_manifest_path = Path(__file__).parent / "manifest.json"
connector = ExcelConnector(json.loads(_manifest_path.read_text()))

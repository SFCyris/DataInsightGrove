from __future__ import annotations

import json as _json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


class SqliteConnector(Connector):
    def _path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            return Path(urlparse(uri).path)
        if uri.startswith("sqlite:///"):
            return Path(uri[len("sqlite:///") :])
        return Path(uri)

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        path = self._path(uri)
        if not path.exists():
            raise FileNotFoundError(f"sqlite file not found: {path}")
        table = (options.get("table") or "").strip()
        query = (options.get("query") or "").strip()
        if not table and not query:
            raise ValueError("sqlite connector: provide either 'table' or 'query'")
        conn = sqlite3.connect(str(path))
        try:
            sql = query if query else f'SELECT * FROM "{table}"'
            df = pl.read_database(sql, connection=conn)
            return df.lazy()
        finally:
            conn.close()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = SqliteConnector(_json.loads(_manifest_path.read_text()))

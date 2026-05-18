from __future__ import annotations

import json as _json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector

# Conservative identifier guard for the ``table`` connector option. Matches
# the regex used by ``export_to_db`` to defeat string-concatenated SQL
# injection — only ASCII alphanumerics + underscore, no leading digit.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
        if table:
            # Validate before string-interpolating into SQL. A table name
            # containing a quote or semicolon would otherwise concatenate
            # arbitrary statements (e.g. ``a"; DROP TABLE x; --``).
            if not _IDENT_RE.match(table):
                raise ValueError(
                    f"sqlite connector: table name {table!r} must match "
                    "^[A-Za-z_][A-Za-z0-9_]*$ (use the 'query' option for "
                    "non-standard names)"
                )
        conn = sqlite3.connect(str(path))
        try:
            sql = query if query else f'SELECT * FROM "{table}"'
            df = pl.read_database(sql, connection=conn)
            return df.lazy()
        finally:
            conn.close()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = SqliteConnector(_json.loads(_manifest_path.read_text()))

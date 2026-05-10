from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.connector import Connector


class MysqlConnector(Connector):
    """Read from MySQL / MariaDB via Polars `read_database_uri`.

    Requires `connectorx` (recommended) or `adbc-driver-mysql` at runtime.
    Install one with `pip install connectorx`.
    """

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        if not (uri.startswith("mysql://") or uri.startswith("mariadb://")):
            raise ValueError(f"mysql connector: URI must start with mysql:// or mariadb:// (got: {uri[:24]}…)")

        table = (options.get("table") or "").strip()
        query = (options.get("query") or "").strip()

        if not table and not query:
            raise ValueError("mysql connector: provide either 'table' or 'query'")

        if query:
            sql = query
        else:
            # MySQL identifiers are backtick-quoted.
            qualified = ".".join(f"`{p}`" for p in table.split("."))
            sql = f"SELECT * FROM {qualified}"

        try:
            df = pl.read_database_uri(query=sql, uri=uri)
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "mysql connector: missing driver. Install one of "
                "`connectorx` or `adbc-driver-mysql` (e.g. `pip install connectorx`)."
            ) from e

        return df.lazy()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = MysqlConnector(_json.loads(_manifest_path.read_text()))

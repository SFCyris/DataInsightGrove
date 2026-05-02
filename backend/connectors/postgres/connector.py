from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.connector import Connector


class PostgresConnector(Connector):
    """Read from PostgreSQL via Polars `read_database_uri`.

    Requires a `connectorx` or `adbc-driver-postgresql` runtime. We let Polars
    pick the available backend; raise a clear error if neither is present.
    """

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        if not (uri.startswith("postgres://") or uri.startswith("postgresql://")):
            raise ValueError(f"postgres connector: URI must start with postgresql:// (got: {uri[:24]}…)")

        table = (options.get("table") or "").strip()
        query = (options.get("query") or "").strip()
        schema = (options.get("schema") or "public").strip()

        if not table and not query:
            raise ValueError("postgres connector: provide either 'table' or 'query'")

        if query:
            sql = query
        else:
            qualified = table if "." in table else f'{schema}."{table}"' if schema else f'"{table}"'
            sql = f"SELECT * FROM {qualified}"

        try:
            df = pl.read_database_uri(query=sql, uri=uri)
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "postgres connector: missing driver. Install one of "
                "`connectorx` or `adbc-driver-postgresql` (e.g. `pip install connectorx`)."
            ) from e

        return df.lazy()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = PostgresConnector(_json.loads(_manifest_path.read_text()))

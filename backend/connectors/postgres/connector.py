from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.connector import Connector


class PostgresConnector(Connector):
    """Read from / write to PostgreSQL via Polars.

    Reads use `read_database_uri` (connectorx or adbc-driver-postgresql at
    runtime). Writes use `write_database` for Reverse-ETL — the
    `export_to_db` step or any sink-mode pipeline output dispatches here.
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

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        """Reverse-ETL write to a Postgres table.

        Uses Polars.write_database. The URI must be a full postgresql:// URI;
        auth happens via the URI's userinfo segment or a saved DIG Connection
        (the executor resolves Connection IDs to URIs before this call).
        """
        if not (uri.startswith("postgres://") or uri.startswith("postgresql://")):
            raise ValueError(
                f"postgres connector: write URI must start with postgresql:// (got: {uri[:24]}…)"
            )

        table = (options.get("table") or "").strip()
        schema = (options.get("schema") or "public").strip()
        if_exists = (options.get("if_exists") or "append").lower()

        if not table:
            raise ValueError("postgres connector: write requires a 'table' option")
        if if_exists not in ("append", "replace", "fail"):
            raise ValueError(
                f"postgres connector: if_exists must be append/replace/fail (got {if_exists!r})"
            )

        qualified = (
            table
            if "." in table
            else f"{schema}.{table}" if schema else table
        )

        try:
            frame.write_database(
                table_name=qualified,
                connection=uri,
                if_table_exists=if_exists,
            )
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "postgres connector: missing driver. Install one of "
                "`adbc-driver-postgresql` or `connectorx` (e.g. "
                "`pip install adbc-driver-postgresql`)."
            ) from e


_manifest_path = Path(__file__).parent / "manifest.json"
connector = PostgresConnector(_json.loads(_manifest_path.read_text()))

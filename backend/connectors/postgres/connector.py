from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.connector import Connector

# Conservative SQL-identifier guard. Postgres allows quoted identifiers with
# arbitrary characters, but the connector's UI surface advertises plain
# table/schema names — restrict to those so a malicious option string
# (``table='a"; DROP TABLE x; --'``) can't break out of the quotes.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_ident(value: str, kind: str) -> str:
    if not _IDENT_RE.match(value):
        raise ValueError(
            f"postgres connector: {kind} {value!r} must match "
            "^[A-Za-z_][A-Za-z0-9_]*$ (use the 'query' option for "
            "non-standard names)"
        )
    return value


def _qualify(schema: str, table: str) -> str:
    """Quote schema.table after validating both halves. The pre-existing
    ``"." in table`` shortcut is preserved (so callers can pass
    ``other_schema.my_table`` in one go) but both pieces are validated."""
    if "." in table:
        schema_part, _, table_part = table.partition(".")
        _validate_ident(schema_part, "schema")
        _validate_ident(table_part, "table")
        return f'"{schema_part}"."{table_part}"'
    _validate_ident(table, "table")
    if schema:
        _validate_ident(schema, "schema")
        return f'"{schema}"."{table}"'
    return f'"{table}"'


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
            qualified = _qualify(schema, table)
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

        qualified = _qualify(schema, table)

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

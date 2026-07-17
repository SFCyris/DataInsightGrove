"""Snowflake reverse-ETL sink connector.

Implements `write()` only — Snowflake reads belong on the warehouse side
(use a Snowflake worksheet, dbt, or the JDBC connector). The write path uses
`snowflake-connector-python`'s `write_pandas` for bulk-load via PUT + COPY
INTO, which handles 10M+ row writes efficiently.

Auth: parsed from the snowflake:// URI's userinfo + query string. For
production deployments use the saved-connection layer so secrets
are at rest in the OS keychain rather than inline in the URI.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import polars as pl

from dig.engine.connector import Connector


class SnowflakeConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        raise NotImplementedError(
            "snowflake connector: source mode not implemented — use the JDBC "
            "connector or read from your warehouse with dbt."
        )

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        if not uri.startswith("snowflake://"):
            raise ValueError(
                f"snowflake connector: URI must start with snowflake:// (got: {uri[:24]}…)"
            )

        try:
            import snowflake.connector
            from snowflake.connector.pandas_tools import write_pandas
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "snowflake connector: missing driver. Install with "
                "`pip install 'snowflake-connector-python[pandas]'` and try again."
            ) from e

        creds = _parse_snowflake_uri(uri)
        table = (options.get("table") or "").strip()
        if not table:
            raise ValueError("snowflake connector: write requires a 'table' option")

        if_exists = (options.get("if_exists") or "append").lower()
        if if_exists not in ("append", "replace", "fail"):
            raise ValueError(
                f"snowflake connector: if_exists must be append/replace/fail (got {if_exists!r})"
            )
        auto_create = bool(options.get("auto_create_table", True))

        # Escape `"` inside the identifier so a value like
        # `bad"; DROP TABLE other; --` becomes `bad""; DROP TABLE other; --`
        # and stays inside the quoted-identifier syntax.
        quoted_table = '"' + table.replace('"', '""') + '"'

        conn = snowflake.connector.connect(**creds)
        try:
            cur = conn.cursor()
            try:
                if if_exists == "replace":
                    cur.execute(f"DROP TABLE IF EXISTS {quoted_table}")
                elif if_exists == "fail":
                    # Scope to the current schema so the same table name in
                    # a different schema doesn't false-positive.
                    cur.execute(
                        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
                        "WHERE TABLE_NAME = %s AND TABLE_SCHEMA = CURRENT_SCHEMA()",
                        (table.upper(),),
                    )
                    if cur.fetchone():
                        raise RuntimeError(
                            f"snowflake connector: table {table!r} exists and if_exists=fail"
                        )
            finally:
                cur.close()

            success, nchunks, nrows, _ = write_pandas(
                conn,
                frame.to_pandas(),
                table_name=table,
                auto_create_table=auto_create,
                quote_identifiers=False,
            )
            if not success:
                raise RuntimeError(
                    f"snowflake connector: write_pandas reported failure ({nchunks} chunks, {nrows} rows)"
                )
        finally:
            conn.close()


def _parse_snowflake_uri(uri: str) -> dict[str, Any]:
    parsed = urlparse(uri)
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    account = parsed.hostname or ""
    parts = [p for p in parsed.path.split("/") if p]
    database = parts[0] if parts else ""
    schema = parts[1] if len(parts) > 1 else "PUBLIC"
    qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    return {
        "user": user,
        "password": password,
        "account": account,
        "warehouse": qs.get("warehouse"),
        "database": database,
        "schema": schema,
        "role": qs.get("role"),
    }


_manifest_path = Path(__file__).parent / "manifest.json"
connector = SnowflakeConnector(_json.loads(_manifest_path.read_text()))

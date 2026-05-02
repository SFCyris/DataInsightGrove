"""export_to_jdbc — write rows to any JDBC-accessible database.

Pairs with the `jdbc` connector (ingress side). Three write modes:

  - append:                INSERT INTO table (...) VALUES (...) for each batch
  - truncate_then_append:  TRUNCATE TABLE table; then append
  - drop_and_create:       DROP TABLE IF EXISTS table; CREATE TABLE table (...);
                           then append. The CREATE statement is built from the
                           Polars schema using a conservative type mapping —
                           good enough for ad-hoc "snapshot to a staging table"
                           workflows; for production schemas, create the table
                           by hand and use append/truncate.

We deliberately reuse the connector module's helpers (env-var resolution,
JAR discovery, jaydebeapi loading) so the auth + driver-management surface
stays in one place.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import polars as pl

from connectors.jdbc.connector import (  # type: ignore[import-not-found]
    _connect,
    _quote_ident,
    _validate_uri,
)
from dig.engine.step import PolarsContext, PolarsResult, Step

log = logging.getLogger(__name__)


# Polars dtype → conservative ANSI SQL type. Used only by drop_and_create.
# We pick widely-supported types; vendor-specific niceties (NUMBER(38,0) on
# Oracle, NVARCHAR(MAX) on SQL Server, etc.) are out of scope — users who
# care about column types create the table themselves and use 'append'.
def _sql_type_for(dtype: pl.DataType) -> str:
    name = str(dtype).lower()
    if name.startswith("int") or name.startswith("uint"):
        return "BIGINT"
    if name in ("float32", "float64") or name.startswith("decimal"):
        return "DOUBLE PRECISION"
    if name == "boolean":
        return "BOOLEAN"
    if name.startswith("date") and "time" not in name:
        return "DATE"
    if name.startswith("datetime") or name.startswith("timestamp"):
        return "TIMESTAMP"
    return "VARCHAR(4000)"


def _create_table_sql(table: str, schema: dict[str, pl.DataType]) -> str:
    cols = ", ".join(
        f"{_quote_ident(name)} {_sql_type_for(dtype)}"
        for name, dtype in schema.items()
    )
    return f"CREATE TABLE {table} ({cols})"


def _insert_sql(table: str, columns: list[str]) -> str:
    col_list = ", ".join(_quote_ident(c) for c in columns)
    placeholders = ", ".join(["?"] * len(columns))
    return f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"


def _batched(rows: list[tuple], size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


class ExportToJdbcStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        url = (params.get("url") or "").strip()
        table = (params.get("table") or "").strip()
        mode = (params.get("mode") or "append").lower()
        batch_size = int(params.get("batchSize") or 1000)

        if not url:
            raise ValueError("export_to_jdbc: 'url' is required")
        if not table:
            raise ValueError("export_to_jdbc: 'table' is required")
        if mode not in ("append", "truncate_then_append", "drop_and_create"):
            raise ValueError(f"export_to_jdbc: invalid mode '{mode}'")
        _validate_uri(url)

        # The connector module's _connect() expects the same shape of options
        # we already accept here, so just re-route. Keeps secret-handling and
        # JAR resolution in one place.
        connect_options = {
            "driverClass": params.get("driverClass"),
            "jarPath": params.get("jarPath"),
            "username": params.get("username"),
            "password": params.get("password"),
        }

        materialized = df.collect() if isinstance(df, pl.LazyFrame) else df
        rows = materialized.rows()
        columns = materialized.columns
        schema = dict(zip(columns, materialized.dtypes))

        conn = _connect(url, connect_options)
        rows_written = 0
        try:
            cursor = conn.cursor()
            try:
                if mode == "drop_and_create":
                    # DROP IF EXISTS — using a generic IF EXISTS clause.
                    # Oracle pre-23 doesn't support it; users on those will
                    # need to switch to truncate_then_append once the table
                    # is created. Documented in the manifest.
                    try:
                        cursor.execute(f"DROP TABLE {table}")
                    except Exception as e:  # noqa: BLE001
                        log.info("export_to_jdbc drop_and_create: ignoring DROP error: %s", e)
                    cursor.execute(_create_table_sql(table, schema))
                elif mode == "truncate_then_append":
                    cursor.execute(f"TRUNCATE TABLE {table}")

                if rows:
                    insert_sql = _insert_sql(table, columns)
                    for batch in _batched(rows, batch_size):
                        cursor.executemany(insert_sql, batch)
                        rows_written += len(batch)
                conn.commit()
            finally:
                cursor.close()
        finally:
            conn.close()

        return PolarsResult(
            output=materialized,
            artifacts=[{
                "kind": "jdbc",
                "url": _redact_url(url),
                "table": table,
                "mode": mode,
                "rows": rows_written,
            }],
        )


def _redact_url(url: str) -> str:
    """Hide an inline password in a JDBC URL before logging.

    Three forms are masked:
      - user:pw@ basic-auth segment (Postgres / MySQL style)
      - ?password=… and &password=… query params
      - ;password=… property segments (SQL Server style — uses semicolons)
    """
    import re
    out = re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1***\3", url)
    out = re.sub(r"([?&;]password=)([^&;]+)", r"\1***", out, flags=re.IGNORECASE)
    return out


step = ExportToJdbcStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

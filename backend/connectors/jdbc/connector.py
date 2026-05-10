"""Generic JDBC source / sink connector.

Bridges DIG to any database that ships a JDBC driver via `jaydebeapi`
(JPype1 underneath). The user supplies:
  - the JDBC URL (e.g. jdbc:postgresql://host:5432/mydb)
  - the driver class (e.g. org.postgresql.Driver)
  - the path to the driver JAR
  - optional username/password
  - either a table name or a SQL query for reads

The JVM is started lazily on first connect and shared across the process
lifetime — subsequent connects to other databases just add their JARs to
the existing classpath. JARs aren't bundled with DIG; the user installs
them once per database vendor.

Why JDBC and not just SQLAlchemy: enterprise DBs (Oracle, DB2, Teradata,
Vertica, Hyperion, …) routinely ship a JDBC driver as the first-class
integration path. Trying to thread native Python drivers for all of them
is a much bigger surface than letting users drop in the JAR they already
have from the vendor.
"""

from __future__ import annotations

import json as _json
import logging
import os
import re
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.connector import Connector

log = logging.getLogger(__name__)


# ${VAR} env-var interpolation used by the password option. Limited to that
# field deliberately — passwords in plain JSON are the highest-value thing
# to redirect via env. URLs and table names rarely need it and supporting
# it everywhere encourages putting secrets in the wrong field.
_ENV_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _resolve_env(value: str | None) -> str | None:
    if value is None or "${" not in value:
        return value
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)


def _validate_uri(uri: str) -> None:
    if not uri.startswith("jdbc:"):
        raise ValueError(
            f"jdbc connector: URI must start with 'jdbc:' (got: {uri[:24]}…). "
            "Example: jdbc:postgresql://host:5432/dbname"
        )


def _import_jaydebeapi():
    try:
        import jaydebeapi  # noqa: PLC0415
        return jaydebeapi
    except ImportError as e:  # noqa: F841
        raise RuntimeError(
            "jdbc connector: missing dependency. Install the [jdbc] extra: "
            "`pip install -e .[jdbc]` (or pip install JPype1 jaydebeapi). "
            "A Java runtime (JRE 8+) must also be on PATH."
        ) from None


def _resolve_jars(jar_path: str) -> list[str]:
    """Expand a file or directory path to a list of .jar files.

    Folder support lets users keep all their drivers in one place
    (`~/dig-drivers/`) and point every JDBC dataset there.
    """
    p = Path(jar_path).expanduser()
    if not p.exists():
        raise FileNotFoundError(
            f"jdbc connector: jarPath '{jar_path}' does not exist. "
            "Provide an absolute path to the JDBC driver .jar file."
        )
    if p.is_dir():
        jars = [str(j) for j in p.glob("*.jar")]
        if not jars:
            raise FileNotFoundError(
                f"jdbc connector: jarPath '{jar_path}' is a directory but contains no .jar files."
            )
        return jars
    return [str(p)]


def _connect(uri: str, options: dict[str, Any]):
    """Open a jaydebeapi connection. Caller is responsible for closing it."""
    jaydebeapi = _import_jaydebeapi()
    driver_class = (options.get("driverClass") or "").strip()
    jar_path = (options.get("jarPath") or "").strip()
    if not driver_class:
        raise ValueError("jdbc connector: 'driverClass' is required")
    if not jar_path:
        raise ValueError("jdbc connector: 'jarPath' is required")
    jars = _resolve_jars(jar_path)

    user = _resolve_env(options.get("username"))
    pw = _resolve_env(options.get("password"))
    driver_args: list[str] | None = None
    if user or pw:
        # jaydebeapi accepts a [user, pw] list as the third positional arg.
        # We always pass both keys when either is set; empty strings are
        # acceptable for some drivers (e.g. trust-auth setups).
        driver_args = [user or "", pw or ""]

    return jaydebeapi.connect(driver_class, uri, driver_args, jars)


def _rows_to_frame(cursor: Any) -> pl.DataFrame:
    """Convert a fetched cursor's result into a Polars DataFrame.

    JDBC types come back through jaydebeapi as native Python objects (int,
    float, str, datetime, decimal.Decimal, bytes, …). Polars infers from
    the values; we only ensure column names are present and that obvious
    bigint/decimal-as-Java-object cases are unwrapped first.
    """
    columns = [d[0] for d in cursor.description] if cursor.description else []
    raw_rows = cursor.fetchall() or []
    # jaydebeapi sometimes returns Java BigDecimal / BigInteger objects that
    # str() cleanly but don't pickle into Arrow. Coerce common cases.
    def _coerce(v: Any) -> Any:
        if v is None:
            return None
        cls = type(v).__name__
        if cls in ("BigDecimal", "BigInteger", "Long"):
            return str(v)
        return v
    rows = [[_coerce(c) for c in r] for r in raw_rows]
    if not columns:
        return pl.DataFrame()
    # Schema inferred from values; explicitly tag column names from the
    # cursor description so order is preserved even for empty results.
    return pl.DataFrame(rows, schema=columns, orient="row")


_TABLE_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$')


def _validate_table_name(table: str) -> str:
    """Reject table names that aren't a plain ``[schema.][catalog.]name``
    identifier. Round-3 pen-tester finding: previously we string-formatted
    the user-supplied ``table`` directly into ``SELECT * FROM {table}``,
    so an authenticated user could supply ``table="x; DROP TABLE users"``
    and trigger second-order SQL injection on whatever JDBC backend they
    pointed at. We now require the table name to match a strict
    identifier pattern (letter / underscore start, alphanumerics +
    underscores after, with up to 2 dot-separated qualifiers for
    schema.table or catalog.schema.table). For exotic identifiers the
    user can drop into ``options.query`` and quote whatever the backend
    accepts.
    """
    if not _TABLE_NAME_RE.match(table):
        raise ValueError(
            f"jdbc connector: 'table' must be a plain identifier "
            f"(letters / digits / underscores / dots), got {table!r}. "
            f"For exotic identifiers, use 'query' with backend-specific quoting."
        )
    return table


class JdbcConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        _validate_uri(uri)
        table = (options.get("table") or "").strip()
        query = (options.get("query") or "").strip()
        if not table and not query:
            raise ValueError("jdbc connector: provide either 'table' or 'query'")
        if table:
            table = _validate_table_name(table)
        sql = query or f"SELECT * FROM {table}"

        conn = _connect(uri, options)
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                df = _rows_to_frame(cursor)
            finally:
                cursor.close()
        finally:
            conn.close()
        return df.lazy()

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        """Append-write `frame` into the configured table.

        For `mode=replace` semantics use the `export_to_jdbc` step, which
        offers explicit truncate/replace/append controls. The connector's
        plain `write` path defaults to append because that's the only mode
        guaranteed to be safe across every JDBC driver.
        """
        _validate_uri(uri)
        table = (options.get("table") or "").strip()
        if not table:
            raise ValueError("jdbc connector: 'table' is required for writes")
        table = _validate_table_name(table)
        if frame.height == 0 and not options.get("writeEmpty"):
            log.info("jdbc write: frame is empty; skipping (set writeEmpty=true to force)")
            return

        cols = frame.columns
        col_list = ", ".join(_quote_ident(c) for c in cols)
        placeholders = ", ".join(["?"] * len(cols))
        insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

        rows = frame.rows()  # list of tuples in column order

        conn = _connect(uri, options)
        try:
            cursor = conn.cursor()
            try:
                cursor.executemany(insert_sql, rows)
                conn.commit()
            finally:
                cursor.close()
        finally:
            conn.close()


def _quote_ident(name: str) -> str:
    """Quote a column identifier for SQL. Uses double quotes (ANSI standard;
    works for Postgres, Oracle, DB2, Snowflake, Vertica). MySQL accepts them
    in ANSI_QUOTES mode. For drivers that require backticks, the user can
    pre-quote in the table name or use the `query` option for reads.
    """
    return '"' + name.replace('"', '""') + '"'


_manifest_path = Path(__file__).parent / "manifest.json"
connector = JdbcConnector(_json.loads(_manifest_path.read_text()))

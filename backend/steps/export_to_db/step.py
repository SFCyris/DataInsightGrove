from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ExportToDbStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        uri = (params.get("uri") or "").strip()
        table = (params.get("table") or "").strip()
        if_exists = (params.get("if_exists") or "append").lower()

        if not uri:
            raise ValueError("export_to_db: 'uri' is required")
        if not table:
            raise ValueError("export_to_db: 'table' is required")
        if if_exists not in ("append", "replace", "fail"):
            raise ValueError(f"export_to_db: invalid if_exists='{if_exists}'")

        # Round-3 pen-tester finding PEN #9: previously the step accepted
        # any URI Polars/SQLAlchemy could parse, which lets an attacker
        # write SQLite files anywhere on disk (`sqlite:////etc/foo.db`)
        # OR pivot a SQL connection at any internal DB host. Validate
        # the scheme + host + path before handing the URI to write_database.
        _assert_db_uri_safe(uri, ctx=ctx)

        # Validate table name shape — same restriction as the JDBC connector.
        # Plain identifier with optional schema/catalog qualifiers; for
        # exotic identifiers the user can pre-process via a custom step.
        import re as _re
        if not _re.match(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$', table):
            raise ValueError(
                f"export_to_db: 'table' must be a plain identifier "
                f"(letters/digits/underscores/dots), got {table!r}."
            )

        try:
            written = df.write_database(table_name=table, connection=uri, if_table_exists=if_exists)
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "export_to_db: missing driver. Install one of "
                "`adbc-driver-sqlite` / `adbc-driver-postgresql` / `adbc-driver-mysql`, "
                "or `sqlalchemy` + the matching DB driver (e.g. `psycopg`)."
            ) from e

        # Polars's write_database returns row count when the underlying driver
        # reports it; otherwise None. Either way, the source df length is the
        # truthful count.
        rows = written if isinstance(written, int) else df.height

        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "db",
                "uri": _redact(uri),
                "table": table,
                "if_exists": if_exists,
                "rows": rows,
            }],
        )


def _redact(uri: str) -> str:
    """Hide any inline password in a connection URI before logging."""
    import re
    return re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1***\3", uri)


_ALLOWED_DB_SCHEMES = frozenset({
    # Local file-backed engines (path validated separately).
    "sqlite",
    # Network-backed engines (host validated against private-IP rules).
    "postgresql", "postgres", "mysql", "mariadb",
    "mssql", "oracle", "snowflake", "bigquery", "redshift",
    "duckdb",
})


def _assert_db_uri_safe(uri: str, *, ctx: PolarsContext | None) -> None:
    """Reject obviously-dangerous DB URIs.

    Two attack vectors blocked:
      * ``sqlite:////etc/foo.db`` — writes a SQLite file anywhere on
        disk. Now constrained to ``data_dir()`` unless
        ``DIG_EXPORT_ALLOW_ABSOLUTE=1``.
      * ``postgresql://internal-db.corp:5432/x`` — SSRF / lateral
        movement. Reject private addresses unless
        ``DIG_REST_ALLOW_PRIVATE=1`` (consistent with the REST connector).
    """
    import os as _os
    from urllib.parse import urlsplit
    parts = urlsplit(uri)
    scheme = parts.scheme.lower().split("+", 1)[0]  # postgresql+psycopg → postgresql
    if scheme not in _ALLOWED_DB_SCHEMES:
        raise ValueError(
            f"export_to_db: scheme {parts.scheme!r} not allowed; permitted: "
            f"{', '.join(sorted(_ALLOWED_DB_SCHEMES))}"
        )
    if scheme == "sqlite":
        # SQLAlchemy SQLite URIs look like sqlite:///relative/path or
        # sqlite:////absolute/path. The path is parts.path or parts.netloc
        # depending on // vs //// — handle both.
        path_str = parts.path
        if not path_str and parts.netloc:
            path_str = parts.netloc
        if path_str.startswith("/"):
            path_str = path_str.lstrip("/")
            absolute = True
        else:
            absolute = False
        if absolute and _os.environ.get("DIG_EXPORT_ALLOW_ABSOLUTE") != "1":
            from dig.engine.uri_safety import assert_local_path_safe
            try:
                assert_local_path_safe("/" + path_str)
            except ValueError as e:
                raise ValueError(
                    f"export_to_db: refusing to write SQLite file at "
                    f"absolute path '/{path_str}'. Set "
                    "DIG_EXPORT_ALLOW_ABSOLUTE=1 to override."
                ) from e
    else:
        # Network DB — validate host isn't private/loopback.
        if _os.environ.get("DIG_REST_ALLOW_PRIVATE") == "1":
            return
        if not parts.hostname:
            return  # SQLAlchemy may handle a hostless URI; let driver complain
        try:
            from connectors.rest_api.connector import _is_private_address
            if _is_private_address(parts.hostname):
                raise ValueError(
                    f"export_to_db: host {parts.hostname!r} resolves to a "
                    "private / loopback / link-local address. Set "
                    "DIG_REST_ALLOW_PRIVATE=1 to permit on a trusted host."
                )
        except ImportError:
            pass


step = ExportToDbStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.connector import Connector

# Same identifier guard as the sqlite/postgres connectors.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
            # MySQL identifiers are backtick-quoted. Each piece must still be
            # validated — a backtick inside the table name closes the quote
            # and lets the rest of the string concatenate arbitrary SQL.
            parts = table.split(".")
            for p in parts:
                if not _IDENT_RE.match(p):
                    raise ValueError(
                        f"mysql connector: table name part {p!r} must match "
                        "^[A-Za-z_][A-Za-z0-9_]*$ (use the 'query' option for "
                        "non-standard names)"
                    )
            qualified = ".".join(f"`{p}`" for p in parts)
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

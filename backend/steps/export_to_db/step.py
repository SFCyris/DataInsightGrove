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


step = ExportToDbStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

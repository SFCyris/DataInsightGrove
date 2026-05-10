"""BigQuery reverse-ETL sink connector.

Implements `write()` only. Auth via service-account JSON path (URI query
string `?credentials=...`) or Application Default Credentials.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import polars as pl

from dig.engine.connector import Connector


class BigQueryConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        raise NotImplementedError(
            "bigquery connector: source mode not implemented — query via dbt or "
            "the BigQuery JDBC driver."
        )

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        if not uri.startswith("bigquery://"):
            raise ValueError(
                f"bigquery connector: URI must start with bigquery:// (got: {uri[:24]}…)"
            )

        try:
            from google.cloud import bigquery  # type: ignore
            from google.oauth2 import service_account  # type: ignore
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "bigquery connector: missing dependency. Install with "
                "`pip install google-cloud-bigquery` and try again."
            ) from e

        parsed = urlparse(uri)
        project = parsed.hostname
        dataset = parsed.path.strip("/")
        if not project or not dataset:
            raise ValueError(
                "bigquery connector: URI must be bigquery://<project>/<dataset>"
            )

        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        credentials_path = qs.get("credentials")

        table = (options.get("table") or "").strip()
        if not table:
            raise ValueError("bigquery connector: write requires a 'table' option")
        if_exists = (options.get("if_exists") or "append").lower()

        write_disposition = {
            "append": "WRITE_APPEND",
            "replace": "WRITE_TRUNCATE",
            "fail": "WRITE_EMPTY",
        }.get(if_exists)
        if not write_disposition:
            raise ValueError(
                f"bigquery connector: if_exists must be append/replace/fail (got {if_exists!r})"
            )

        if credentials_path:
            creds = service_account.Credentials.from_service_account_file(credentials_path)
            client = bigquery.Client(project=project, credentials=creds)
        else:
            client = bigquery.Client(project=project)

        table_ref = f"{project}.{dataset}.{table}"
        job_config = bigquery.LoadJobConfig(write_disposition=write_disposition)
        job = client.load_table_from_dataframe(
            frame.to_pandas(), table_ref, job_config=job_config
        )
        job.result()


_manifest_path = Path(__file__).parent / "manifest.json"
connector = BigQueryConnector(_json.loads(_manifest_path.read_text()))

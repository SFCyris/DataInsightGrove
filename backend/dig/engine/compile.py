"""Compile a Pipeline to SQL + virtual-file bindings for DuckDB-WASM execution.

The compile path used by the *backend* executor reads CSV/Parquet from the
local filesystem. For the browser we need to:

  1. Express each dataset as a `read_xxx('<vfs_name>')` call.
  2. Tell the frontend which URL to register under that VFS name.

This module returns both, plus the dialect-tagged SQL the frontend will execute
in DuckDB-WASM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from dig.engine.dag import topo_sort, validate
from dig.engine.pipeline import Pipeline
from dig.engine.registry import steps
from dig.engine.step import quote_ident, quote_str


@dataclass
class FileBinding:
    name: str  # virtual filename used inside the SQL, e.g. "ds_customers.parquet"
    url: str  # URL the frontend should fetch (relative path; UI prefixes API_BASE)
    format: str  # "parquet" | "csv"


@dataclass
class CompileResult:
    sql: str
    files: list[FileBinding] = field(default_factory=list)
    terminal: str | None = None  # alias of the terminal CTE


def compile_for_browser(p: Pipeline, *, terminal: str | None = None) -> CompileResult:
    """Compile pipeline to SQL + binding info for DuckDB-WASM.

    Currently every dataset must already exist as a Phase-1 cached parquet — i.e.
    the dataset spec has connector='parquet' and uri pointing at the cached
    file. (Pipelines built in the canvas always use this form.) Pipelines that
    reference raw CSVs by path can run on the backend but not in the browser
    until we add WASM-side file uploads.
    """
    validate(p)
    sorted_nodes = topo_sort(p)

    files: list[FileBinding] = []
    ctes: list[str] = []

    for d in p.datasets:
        if d.connector == "parquet":
            # Use the dataset id as a stable virtual filename.
            vname = f"{d.id}.parquet"
            # If the URI looks like a backend cached path, derive a download URL.
            url = _derive_download_url(d.uri, d.id)
            files.append(FileBinding(name=vname, url=url, format="parquet"))
            ctes.append(
                f"{quote_ident(d.id)} AS (SELECT * FROM read_parquet({quote_str(vname)}))"
            )
        elif d.connector == "csv":
            vname = f"{d.id}.csv"
            url = _derive_download_url(d.uri, d.id)
            files.append(FileBinding(name=vname, url=url, format="csv"))
            delim = d.options.get("delimiter", ",")
            if delim == "\\t":
                delim = "\t"
            header = d.options.get("header", True)
            ctes.append(
                f"{quote_ident(d.id)} AS ("
                f"SELECT * FROM read_csv_auto({quote_str(vname)}, "
                f"delim={quote_str(delim)}, header={'true' if header else 'false'}))"
            )
        else:
            raise ValueError(
                f"compile_for_browser: connector '{d.connector}' not browser-runnable yet"
            )

    for node in sorted_nodes:
        step = steps().get(node.step)
        if step.engine_browser != "sql":
            raise ValueError(
                f"step '{step.id}' has browser engine '{step.engine_browser}'; only 'sql' is supported in compile_for_browser"
            )
        inputs: dict[str, str] = {
            port: quote_ident(ref.ref) for port, ref in node.inputs.items()
        }
        body = step.to_sql(node.params, inputs)
        ctes.append(f"{quote_ident(node.id)} AS ({body})")

    last_alias = terminal or (sorted_nodes[-1].id if sorted_nodes else None)
    if last_alias is None:
        if p.datasets:
            last_alias = p.datasets[0].id
        else:
            raise ValueError("pipeline has no nodes and no datasets")

    sql = f"WITH {', '.join(ctes)} SELECT * FROM {quote_ident(last_alias)}"
    return CompileResult(sql=sql, files=files, terminal=last_alias)


def _derive_download_url(uri: str, dataset_id: str) -> str:
    """Turn a `file:///…/data/datasets/<ULID>.parquet` URI into an API URL the
    browser can fetch from. The pipeline's internal dataset alias (e.g. 'ds_c')
    isn't the same as the Dataset row's ULID — extract the ULID from the path."""
    if uri.startswith("file://"):
        path = urlparse(uri).path
        if "/data/datasets/" in path:
            # filename = <ULID>.parquet
            from pathlib import Path

            ulid = Path(path).stem
            return f"/datasets/{ulid}/cached.parquet"
    return uri

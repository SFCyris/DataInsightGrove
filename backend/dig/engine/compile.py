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

from dig.engine.dag import infer_schemas, topo_sort, validate
from dig.engine.pipeline import Pipeline, effective_connector
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


_VALID_JOIN_VIEW_MODES = {"matched", "unmatched_left", "unmatched_right"}


def compile_for_browser(
    p: Pipeline,
    *,
    terminal: str | None = None,
    terminal_view_mode: str | None = None,
) -> CompileResult:
    """Compile pipeline to SQL + binding info for DuckDB-WASM.

    Currently every dataset must already exist as a cached parquet — i.e.
    the dataset spec has connector='parquet' and uri pointing at the cached
    file. (Pipelines built in the canvas always use this form.) Pipelines that
    reference raw CSVs by path can run on the backend but not in the browser
    until we add WASM-side file uploads.

    When `terminal` is given, only nodes that feed the terminal (its
    transitive ancestors plus itself) are compiled. Sibling branches —
    e.g. a separate chart step in the same pipeline — are skipped. This
    matters when a pipeline mixes browser-runnable steps with non-SQL
    steps (charts, forecasts): the error reported here should reference
    the step the user is *actually* trying to preview, not whichever
    non-SQL step happens to come first in topological order.
    """
    validate(p)
    sorted_nodes = topo_sort(p)
    if terminal is not None:
        # Walk back from `terminal` collecting ancestors; restrict the
        # compile loop to that set so unrelated non-SQL steps in other
        # branches don't trigger a misleading error.
        nodes_by_id = {n.id: n for n in p.nodes}
        if terminal in nodes_by_id:
            keep: set[str] = set()
            queue = [terminal]
            while queue:
                nid = queue.pop()
                if nid in keep:
                    continue
                keep.add(nid)
                node = nodes_by_id.get(nid)
                if node is None:
                    continue
                for ref in node.inputs.values():
                    if ref.ref in nodes_by_id:
                        queue.append(ref.ref)
            sorted_nodes = [n for n in sorted_nodes if n.id in keep]
        elif any(d.id == terminal for d in p.datasets):
            # Terminal is a registered dataset alias (a root). No node
            # is an ancestor of a dataset — drop them all so e.g. an
            # unconfigured downstream join doesn't fail the dataset's
            # own preview.
            sorted_nodes = []

    # Infer schemas across the pipeline so SQL builders that benefit
    # from explicit per-input schemas (notably the join step's
    # collision-resolution + outputColumns logic) get them. We pass
    # the result through `input_schemas` to each step's `to_sql`.
    # If schema inference throws (a partially-configured sibling
    # branch, say), we degrade to no-schemas and steps fall back to
    # their schema-less SQL — same behaviour as before this addition.
    try:
        all_schemas = infer_schemas(p)
    except Exception:
        all_schemas = {}

    files: list[FileBinding] = []
    ctes: list[str] = []

    for d in p.datasets:
        # Trust the URI extension over the persisted connector — the bytes
        # on disk are the source of truth. Fixes pipelines whose docs were
        # saved with connector='csv' before the dataset was re-cached as
        # parquet (or vice-versa).
        conn = effective_connector(d)
        if conn == "parquet":
            # Use the dataset id as a stable virtual filename.
            vname = f"{d.id}.parquet"
            # If the URI looks like a backend cached path, derive a download URL.
            url = _derive_download_url(d.uri, d.id)
            files.append(FileBinding(name=vname, url=url, format="parquet"))
            ctes.append(
                f"{quote_ident(d.id)} AS (SELECT * FROM read_parquet({quote_str(vname)}))"
            )
        elif conn == "csv":
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
                f"compile_for_browser: connector '{conn}' not browser-runnable yet"
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
        node_input_schemas: dict[str, dict[str, str]] = {
            port: all_schemas.get(ref.ref, {}) for port, ref in node.inputs.items()
        }
        # When the user has flipped the focused-join's view to
        # `unmatched_left` / `unmatched_right`, override the kind for
        # *only* the terminal join node. The semantics are identical to
        # an anti-join, so we re-use that path — projection collapses
        # to one side's columns, which is what the diagnostic surface
        # wants ("show me the left rows that didn't match").
        params = node.params
        if (
            terminal is not None
            and node.id == terminal
            and node.step == "join"
            and terminal_view_mode in {"unmatched_left", "unmatched_right"}
        ):
            params = {
                **params,
                "kind": "anti_left" if terminal_view_mode == "unmatched_left" else "anti_right",
            }
        # Keep tolerant of older steps that don't take input_schemas —
        # try with the kwarg first; on TypeError fall back to without.
        try:
            body = step.to_sql(params, inputs, input_schemas=node_input_schemas)
        except TypeError:
            body = step.to_sql(params, inputs)
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

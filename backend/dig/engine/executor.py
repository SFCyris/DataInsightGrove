"""Backend pipeline executor — compiles to one DuckDB SQL statement and runs it.

The compiled form looks like:

    WITH
      ds_customers AS (SELECT * FROM read_csv_auto('…')),
      n_filter    AS (SELECT * FROM ds_customers WHERE …),
      n_sort      AS (SELECT * FROM n_filter ORDER BY …)
    SELECT * FROM n_sort

Where each step's `to_sql(params, inputs)` provides the body of its CTE and
`inputs` maps port name to the upstream alias.

Outputs are written one at a time:
  - if a sink is configured, materialize via the connector
  - always: write a Parquet snapshot per output to data/outputs/<run_id>/<output_name>.parquet
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb

from dig.engine.dag import infer_schemas, topo_sort, validate
from dig.engine.pipeline import Node, OutputSpec, Pipeline, Reference, effective_connector
from dig.engine.registry import connectors, steps
from dig.engine.step import NanOrigin, PolarsContext, PolarsResult, Step, quote_ident, quote_str
from dig.storage.files import data_dir

log = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    runId: str
    outputs: dict[str, str]  # output id -> parquet path
    rowCounts: dict[str, int]
    elapsedMs: int
    # Free-form artifacts produced by Polars-engine steps (export_to_image, …).
    # Shape: { output_id: [ {kind, path?, table?, mime?, …}, … ] }
    artifacts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Per-node execution metrics for the canvas run-state overlay
    # (Phase A Layer 1). Shape: { node_id: { rows_out?, elapsed_ms?,
    # status: "success"|"failed"|"skipped" } }. Populated for Polars
    # nodes (we have the dataframe) and terminal output nodes (we count
    # the parquet). SQL-only intermediate nodes are marked "success"
    # without row counts — cheap recompute if needed.
    nodeMetrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Per-node NaN-origin sidecars — surfaced by the grid as the
    # orange-⚠ NULL variant on the step that produced the failure.
    # Shape: { node_id: [ {column, row_indices, cause, source_column?}, … ] }.
    # See `internal/proposals/NULL_AND_NAN_DISPLAY.md`. Each entry lives on
    # the producing step ONLY; the next step sees plain NULL because the
    # executor coerces NaN→None after capturing this record.
    nanOrigins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def _ref_alias(ref: Reference) -> str:
    return ref.ref


# Cap row-index lists at 10k per (node, column) tuple — keeps the run JSON
# payload bounded. Above the cap we record only the first N indices plus a
# `truncated_count`; the column-header badge still shows the full count.
_NAN_ORIGIN_ROW_CAP = 10_000


def _scan_and_coerce_nan(
    result: PolarsResult,
    *,
    run_id: str,
    pipeline_id: str | None,
    node_id: str,
    step_id: str,
) -> list[dict[str, Any]]:
    """Post-step hook — scan float columns for NaN/±Inf, coerce them to
    NULL on the output frame, attach the row-index sidecar.

    Mutates `result.output` (in-place via `with_columns`) and appends to
    `result.nan_origins`. Returns the JSON-serialisable form of the
    origins for this step's output, suitable for storing in the run's
    `nanOrigins` payload.

    Emits a `data.nan.produced` event per (column, cause) tuple. Best-
    effort: emit failures are swallowed so they never break the run.

    Cast steps that produce non-float outputs (string→Int with bad rows
    becoming NULL directly, not NaN) pre-populate `result.nan_origins`
    BEFORE the scanner runs; this helper does not overwrite those.
    """
    import polars as pl

    # Preserve any pre-populated entries (cast steps for non-float targets).
    pre_existing = list(result.nan_origins)
    new_entries: list[NanOrigin] = []

    df = result.output
    for col, dtype in df.schema.items():
        if dtype not in (pl.Float32, pl.Float64):
            continue
        # Split is_nan vs is_infinite so we can record `arithmetic_nan`
        # vs `arithmetic_inf` distinctly (telemetry uses this; the
        # tooltip collapses both to "computation failed").
        nan_mask = df[col].is_nan()
        inf_mask = df[col].is_infinite()
        if not (nan_mask.any() or inf_mask.any()):
            continue
        if nan_mask.any():
            indices = [int(i) for i, v in enumerate(nan_mask.to_list()) if v]
            new_entries.append(NanOrigin(
                column=col, row_indices=indices,
                cause="arithmetic_nan", source_column=None,
            ))
        if inf_mask.any():
            indices = [int(i) for i, v in enumerate(inf_mask.to_list()) if v]
            new_entries.append(NanOrigin(
                column=col, row_indices=indices,
                cause="arithmetic_inf", source_column=None,
            ))
        # Coerce in place: both NaN and ±Inf become NULL on this step's
        # persisted output. fill_nan handles NaN; the explicit when/then
        # below catches ±Inf which fill_nan does not.
        coerced = (
            pl.when(df[col].is_nan() | df[col].is_infinite())
            .then(None)
            .otherwise(pl.col(col))
            .alias(col)
        )
        df = df.with_columns(coerced)
    result.output = df
    result.nan_origins = pre_existing + new_entries

    # Telemetry — emit one event per (column, cause). Logged + swallowed
    # on failure so the run never breaks because of a telemetry hiccup.
    if result.nan_origins:
        try:
            import asyncio
            from dig.api.events import EventKinds, emit_event

            async def _emit_all() -> None:
                for origin in result.nan_origins:
                    await emit_event(
                        EventKinds.DATA_NAN_PRODUCED,
                        run_id=run_id,
                        pipeline_id=pipeline_id,
                        node_id=node_id,
                        step_id=step_id,
                        column=origin.column,
                        cause=origin.cause,
                        source_column=origin.source_column,
                        count=len(origin.row_indices),
                    )

            # We're in a worker thread under JobManager. Reuse the main loop
            # if alive; otherwise spin a one-shot loop (test/script path).
            try:
                from dig.jobs.manager import main_loop as _main_loop
                api_loop = _main_loop()
            except Exception:
                api_loop = None
            if api_loop is not None and api_loop.is_running():
                asyncio.run_coroutine_threadsafe(_emit_all(), api_loop)
            else:
                try:
                    asyncio.run(_emit_all())
                except RuntimeError:
                    # Best-effort: skip if we're already inside a running loop.
                    pass
        except Exception:
            log.exception("nan-origin event emit failed for node %s", node_id)

    return [_nan_origin_to_dict(o) for o in result.nan_origins]


def _nan_origin_to_dict(o: NanOrigin) -> dict[str, Any]:
    """JSON-serialise a NanOrigin, capping row_indices at `_NAN_ORIGIN_ROW_CAP`."""
    indices = o.row_indices
    payload: dict[str, Any] = {
        "column": o.column,
        "cause": o.cause,
        "count": len(indices),
    }
    if o.source_column is not None:
        payload["source_column"] = o.source_column
    if len(indices) > _NAN_ORIGIN_ROW_CAP:
        payload["row_indices"] = indices[:_NAN_ORIGIN_ROW_CAP]
        payload["truncated"] = True
    else:
        payload["row_indices"] = indices
        payload["truncated"] = False
    return payload


LINEAGE_COL_PREFIX = "__dig_lineage_"


def _track_lineage(p: Pipeline) -> bool:
    return bool((p.metadata or {}).get("trackLineage"))


def _dataset_cte(p: Pipeline, dataset_id: str) -> str:
    """Build the CTE body that loads a dataset via DuckDB's native readers when possible.

    When pipeline.metadata.trackLineage is true, append a per-row index
    column `__dig_lineage_<dataset_id>` so we can trace output rows back to
    their source.
    """
    spec = next(d for d in p.datasets if d.id == dataset_id)
    # Trust the URI extension when it disagrees with the persisted
    # connector — see effective_connector docstring for the rationale.
    conn = effective_connector(spec)
    if conn == "csv":
        # Use DuckDB's read_csv_auto for speed; let it sniff types like our connector does.
        path = urlparse(spec.uri).path if spec.uri.startswith("file://") else spec.uri
        delim = spec.options.get("delimiter", ",")
        if delim == "\\t":
            delim = "\t"
        header = spec.options.get("header", True)
        body = (
            f"SELECT * FROM read_csv_auto({quote_str(path)}, "
            f"delim={quote_str(delim)}, header={'true' if header else 'false'})"
        )
    elif conn == "parquet":
        path = urlparse(spec.uri).path if spec.uri.startswith("file://") else spec.uri
        body = f"SELECT * FROM read_parquet({quote_str(path)})"
    else:
        raise ValueError(f"executor: unsupported connector '{conn}'")

    if _track_lineage(p):
        lineage_col = quote_ident(f"{LINEAGE_COL_PREFIX}{dataset_id}")
        return (
            f"SELECT *, row_number() OVER () AS {lineage_col} FROM ({body})"
        )
    return body


# Cache: Step subclass → does its `to_sql` accept the `input_schemas` kwarg?
# Detected via `inspect.signature` once per class. Steps that opt in receive
# the upstream schema so they can position columns by name (add_column) or do
# any other schema-aware compilation; steps that don't opt in are called the
# old two-arg way and pay no cost.
_TO_SQL_WANTS_SCHEMAS: dict[type[Step], bool] = {}


def _wants_schemas(step: Step) -> bool:
    cls = type(step)
    cached = _TO_SQL_WANTS_SCHEMAS.get(cls)
    if cached is None:
        try:
            cached = "input_schemas" in inspect.signature(step.to_sql).parameters
        except (TypeError, ValueError):
            cached = False
        _TO_SQL_WANTS_SCHEMAS[cls] = cached
    return cached


def compile_to_sql(
    p: Pipeline,
    *,
    terminal: str | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    """Compile pipeline to a single SQL string. `terminal` selects the final SELECT alias.

    If `terminal` is None, the last node in topo order is used.

    `overrides` maps node id → parquet path; nodes in this map are emitted as
    `<id> AS (SELECT * FROM read_parquet('<path>'))` instead of going through
    the step's `to_sql`. Used for Polars-engine nodes that have already been
    materialized.
    """
    validate(p)
    sorted_nodes = topo_sort(p)
    ctes: list[str] = []
    overrides = overrides or {}

    # Restrict to terminal's ancestors when given. Without this, an
    # unconfigured downstream step (e.g. a `join` with empty keys
    # added but not yet wired) breaks previews of upstream nodes
    # that don't depend on it. Same restriction `compile_for_browser`
    # already applies; both must agree because the dispatcher routes
    # through whichever can handle the chain.
    if terminal is not None:
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
            # Dataset terminal — datasets are roots, no node is its
            # ancestor. Drop all nodes so the SELECT just reads the
            # dataset's CTE.
            sorted_nodes = []

    # Dataset CTEs.
    for d in p.datasets:
        body = _dataset_cte(p, d.id)
        ctes.append(f"{quote_ident(d.id)} AS ({body})")

    # Inferred schemas — only computed if at least one step in this pipeline
    # opts in via the `input_schemas` kwarg on its `to_sql`. Datasets are
    # probed via the connector (cheap; reads file header only).
    inferred: dict[str, dict[str, str]] | None = None

    # Step CTEs in topo order.
    for node in sorted_nodes:
        if node.id in overrides:
            ctes.append(
                f"{quote_ident(node.id)} AS (SELECT * FROM read_parquet({quote_str(overrides[node.id])}))"
            )
            continue
        step = steps().get(node.step)
        # Map port -> upstream alias quoted as identifier.
        inputs: dict[str, str] = {}
        for port, ref in node.inputs.items():
            inputs[port] = quote_ident(ref.ref)
        if _wants_schemas(step):
            if inferred is None:
                inferred = infer_schemas(p)
            input_schemas = {
                port: inferred.get(ref.ref, {}) for port, ref in node.inputs.items()
            }
            body = step.to_sql(node.params, inputs, input_schemas=input_schemas)
        else:
            body = step.to_sql(node.params, inputs)
        ctes.append(f"{quote_ident(node.id)} AS ({body})")

    last_alias = terminal or (sorted_nodes[-1].id if sorted_nodes else None)
    if last_alias is None:
        # No nodes; just SELECT from the first dataset if any.
        if p.datasets:
            return f"WITH {', '.join(ctes)} SELECT * FROM {quote_ident(p.datasets[0].id)}"
        raise ValueError("pipeline has no datasets and no nodes")

    return f"WITH {', '.join(ctes)} SELECT * FROM {quote_ident(last_alias)}"


def _materialize_sql_to_polars(con: duckdb.DuckDBPyConnection, sql: str):
    """Run a DuckDB SQL and return a Polars DataFrame."""
    return con.execute(sql).pl()


def _terminal_polars_node(p: Pipeline, terminal: str) -> Node | None:
    """Return the node identified by `terminal` if it's a Polars-engine step,
    else None."""
    node = next((n for n in p.nodes if n.id == terminal), None)
    if node is None:
        return None
    try:
        step = steps().get(node.step)
    except KeyError:
        return None
    return node if step.engine_primary == "polars" else None


def materialize_polars_ancestors(
    con: "duckdb.DuckDBPyConnection",
    p: Pipeline,
    terminal: str,
    *,
    out_dir: Path,
    sample_rows: int | None,
    run_id: str = "__preview",
    pipeline_chain: tuple[str, ...] = (),
) -> dict[str, str]:
    """Pre-materialise every Polars-engine step that's an ancestor of the
    given ``terminal`` node, writing each one's output to a parquet file
    under ``out_dir`` and returning a ``{node_id: path}`` dict suitable
    for ``compile_to_sql(overrides=...)``.

    This is the live-preview analogue of the executor's main pre-materialise
    loop (executor.run): it gives the preview path the same correct
    semantics for chains where a Polars step feeds another Polars step
    feeds a chart. Without this, the chart-rendering ``preview-step``
    endpoint would call ``compile_to_sql`` on the raw Polars-step input
    and the chart would render against rows that don't include the
    upstream Polars step's added columns.

    Visits ancestors only (not the terminal itself nor sibling branches),
    in topological order. SQL ancestors of Polars steps are inlined into
    the CTE chain via the ``overrides`` mechanism — they don't need
    separate parquet files.
    """
    import polars as pl

    # Walk back from `terminal` collecting ancestor node ids.
    nodes_by_id = {n.id: n for n in p.nodes}
    ancestors: set[str] = set()
    queue = [terminal]
    while queue:
        nid = queue.pop()
        if nid in ancestors:
            continue
        node = nodes_by_id.get(nid)
        if node is None:
            continue
        if nid != terminal:
            ancestors.add(nid)
        for ref in node.inputs.values():
            if ref.ref in nodes_by_id:
                queue.append(ref.ref)

    materialized: dict[str, str] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    for node in topo_sort(p):
        if node.id not in ancestors:
            continue
        try:
            step = steps().get(node.step)
        except KeyError:
            continue
        if step.engine_primary != "polars":
            continue
        # Materialise this Polars ancestor — SQL inputs are built using
        # the running `materialized` dict so chains-of-polars work.
        input_frames: dict[str, pl.DataFrame] = {}
        for port, ref in node.inputs.items():
            up_sql = compile_to_sql(p, terminal=ref.ref, overrides=materialized)
            if sample_rows:
                up_sql = f"{up_sql} LIMIT {int(sample_rows)}"
            input_frames[port] = _materialize_sql_to_polars(con, up_sql)
        from dig.engine.step import PolarsContext  # local: avoid module cycle
        ctx = PolarsContext(
            run_id=run_id, out_dir=out_dir, node_id=node.id, pipeline_chain=pipeline_chain,
        )
        try:
            res = step.execute_polars(input_frames, node.params, ctx)
        except Exception as e:
            raise RuntimeError(
                f"polars step '{node.id}' ({step.id}) failed during preview: {e}"
            ) from e
        intermed_path = out_dir / f"{node.id}.parquet"
        res.output.write_parquet(intermed_path, compression="zstd")
        materialized[node.id] = str(intermed_path)
    return materialized


def _run_one_output(
    con: duckdb.DuckDBPyConnection,
    p: Pipeline,
    o: OutputSpec,
    *,
    out_dir: Path,
    run_id: str,
    sample_rows: int | None,
    materialized: dict[str, str] | None = None,
    pipeline_chain: tuple[str, ...] = (),
) -> tuple[str, int, list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Run the pipeline up to this output and write a parquet snapshot.

    Returns (parquet_path, row_count, artifacts, columns, nan_origins).
    `columns` lists the output's column names — used by the post-run
    drift detector to spot schema changes vs the prior succeeded run.
    `nan_origins` is the post-step sidecar (empty for SQL-only outputs;
    populated for Polars terminal steps that produced NaN/±Inf).
    """
    terminal = o.from_.ref
    out_path = out_dir / f"{o.name}.parquet"
    artifacts: list[dict[str, Any]] = []
    nan_origins: list[dict[str, Any]] = []
    materialized = dict(materialized or {})

    poly_node = _terminal_polars_node(p, terminal)

    if poly_node is not None:
        # Polars-engine terminal step. Compile SQL up to (but not including)
        # this node's inputs, materialize to Polars frames, then call
        # execute_polars. The step is responsible for any side effects; we
        # always persist its output as a parquet snapshot for the run record.
        import polars as pl

        step = steps().get(poly_node.step)
        input_frames: dict[str, pl.DataFrame] = {}
        for port, ref in poly_node.inputs.items():
            up_sql = compile_to_sql(p, terminal=ref.ref, overrides=materialized)
            if sample_rows:
                up_sql = f"{up_sql} LIMIT {int(sample_rows)}"
            input_frames[port] = _materialize_sql_to_polars(con, up_sql)

        ctx = PolarsContext(
            run_id=run_id, out_dir=out_dir, node_id=poly_node.id, pipeline_chain=pipeline_chain,
        )
        try:
            result = step.execute_polars(input_frames, poly_node.params, ctx)
        except Exception as e:
            raise RuntimeError(f"polars step '{poly_node.id}' ({step.id}) failed: {e}") from e

        # Post-step NaN scan + coerce before persisting the parquet.
        try:
            nan_origins = _scan_and_coerce_nan(
                result, run_id=run_id, pipeline_id=p.id,
                node_id=poly_node.id, step_id=step.id,
            )
        except Exception:
            log.exception("nan-scan failed for terminal node %s — proceeding without sidecar", poly_node.id)
            nan_origins = []

        df = result.output
        df.write_parquet(out_path, compression="zstd")
        artifacts.extend(result.artifacts)
        row_count = df.height
    else:
        # Pure SQL pipeline (possibly with materialized Polars-step parquets).
        sql = compile_to_sql(p, terminal=terminal, overrides=materialized)
        if sample_rows:
            sql = f"{sql} LIMIT {int(sample_rows)}"
        log.info("[run %s] output %s SQL: %s", run_id, o.id, sql[:240])
        con.execute(
            f"COPY ({sql}) TO {quote_str(str(out_path))} (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        row_count = con.execute(
            f"SELECT count(*) FROM read_parquet({quote_str(str(out_path))})"
        ).fetchone()[0]

    # If a sink is declared, materialize via the connector too.
    if o.sink is not None:
        sink_connector = connectors().get(o.sink.connector)
        import polars as pl

        df = pl.read_parquet(out_path)
        sink_connector.write(df, o.sink.uri, o.sink.options)
        artifacts.append({
            "kind": "sink",
            "connector": o.sink.connector,
            "uri": o.sink.uri,
            "rows": row_count,
        })

    # Capture column names from the parquet metadata. Cheap — reads
    # the parquet footer only, not the data. Used by the drift
    # detector after the run completes.
    try:
        import polars as pl
        columns = list(pl.read_parquet_schema(str(out_path)).keys())
    except Exception:
        log.exception("could not read parquet schema for output %s", o.id)
        columns = []

    return str(out_path), row_count, artifacts, columns, nan_origins


def execute_subpipeline(
    pipeline_id: str,
    *,
    output_id: str | None,
    sample_rows: int | None,
    chain: tuple[str, ...],
):
    """Resolve a saved pipeline by id and run it; return (DataFrame, name).

    Synchronous + uses its own engine connection. Imported lazily by the
    subpipeline step. The chain argument carries the ancestor pipeline ids
    so the inner execute() can pass them on for cycle detection.
    """
    import asyncio

    import polars as pl

    from dig.storage.db import SessionLocal
    from dig.storage.models import Pipeline as PipelineRow
    from ulid import ULID

    async def _load() -> PipelineRow | None:
        async with SessionLocal() as session:
            return await session.get(PipelineRow, pipeline_id)

    # We're inside a worker thread spawned by JobManager via `to_thread` —
    # `asyncio.get_event_loop()` is deprecated here (3.10+) and raises in
    # 3.12+, and opening a fresh loop via `asyncio.run` strands the aiosqlite
    # engine on the wrong loop. Use the main loop captured by JobManager.
    from dig.jobs.manager import main_loop as _main_loop

    api_loop = _main_loop()
    if api_loop is not None and api_loop.is_running():
        row = asyncio.run_coroutine_threadsafe(_load(), api_loop).result()
    else:
        # Fallback for direct callers (tests, scripts) where no JobManager
        # has run a submit yet. A fresh loop is fine here because no other
        # coroutine has registered against `SessionLocal`'s engine.
        row = asyncio.run(_load())

    if row is None:
        raise ValueError(f"subpipeline: pipeline '{pipeline_id}' not found")

    inner_doc = row.document or {}
    p = Pipeline.model_validate(inner_doc)

    inner_run_id = str(ULID())
    inner = execute(
        p,
        run_id=inner_run_id,
        sample_rows=sample_rows,
        _pipeline_chain=(*chain, pipeline_id),
    )
    # Pick the first output if not specified, else find by id.
    if not inner.outputs:
        raise ValueError(f"subpipeline: '{pipeline_id}' produced no outputs")
    out_path: str | None = None
    if output_id:
        out_path = inner.outputs.get(output_id)
        if out_path is None:
            raise ValueError(
                f"subpipeline: output '{output_id}' not found in '{pipeline_id}' "
                f"(available: {sorted(inner.outputs)})"
            )
    else:
        out_path = next(iter(inner.outputs.values()))

    df = pl.read_parquet(out_path)
    return df, str(row.name or pipeline_id)


def execute(
    p: Pipeline,
    *,
    run_id: str,
    sample_rows: int | None = None,
    _pipeline_chain: tuple[str, ...] = (),
) -> ExecutionResult:
    """Execute the pipeline and write each output to a parquet file under data/outputs/<run_id>/.

    sample_rows: if set, append a LIMIT to each output query (useful for previews).
    """
    import time

    started = time.perf_counter()
    validate(p)

    out_dir = data_dir() / "outputs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(database=":memory:")
    outputs: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    artifacts: dict[str, list[dict[str, Any]]] = {}
    # Per-node metrics for the canvas Layer 1 overlay. Keyed by node id;
    # values are { rows_out?, elapsed_ms?, status }. Polars-engine nodes
    # populate row counts cheaply (dataframe is already materialized);
    # SQL-intermediate nodes get a status-only entry.
    node_metrics: dict[str, dict[str, Any]] = {}
    # Per-node NaN-origin sidecars — populated by _scan_and_coerce_nan.
    # See ExecutionResult.nanOrigins.
    nan_origins_by_node: dict[str, list[dict[str, Any]]] = {}

    try:
        pipeline_outputs: list[OutputSpec] = list(p.outputs)
        if not pipeline_outputs:
            # Implicit: yield the last node as a single output.
            sorted_nodes = topo_sort(p)
            if not sorted_nodes:
                raise ValueError("pipeline has no nodes and no outputs")
            last = sorted_nodes[-1]
            pipeline_outputs = [
                OutputSpec(
                    id=f"o_{last.id}",
                    name=last.id,
                    **{"from": Reference(ref=last.id, port=last.outputs[0])},
                )
            ]

        # Pre-materialize Polars-engine nodes that aren't terminal outputs of the
        # pipeline. Their results are written to parquet under out_dir/_intermediate/
        # and their CTEs in subsequent SQL compilations read from those parquets.
        terminal_node_ids = {o.from_.ref for o in pipeline_outputs}
        intermediate_dir = out_dir / "_intermediate"
        materialized: dict[str, str] = {}
        for node in topo_sort(p):
            if node.id in terminal_node_ids:
                continue
            try:
                step = steps().get(node.step)
            except KeyError:
                continue
            if step.engine_primary != "polars":
                continue
            # Materialize this Polars node now, using SQL to build its inputs.
            intermediate_dir.mkdir(parents=True, exist_ok=True)
            import polars as pl

            input_frames: dict[str, pl.DataFrame] = {}
            for port, ref in node.inputs.items():
                up_sql = compile_to_sql(p, terminal=ref.ref, overrides=materialized)
                if sample_rows:
                    up_sql = f"{up_sql} LIMIT {int(sample_rows)}"
                input_frames[port] = _materialize_sql_to_polars(con, up_sql)
            ctx = PolarsContext(
                run_id=run_id, out_dir=out_dir, node_id=node.id, pipeline_chain=_pipeline_chain,
            )
            node_started = time.perf_counter()
            try:
                res = step.execute_polars(input_frames, node.params, ctx)
            except Exception as e:
                node_metrics[node.id] = {
                    "status": "failed",
                    "elapsed_ms": int((time.perf_counter() - node_started) * 1000),
                    "error": f"{type(e).__name__}: {e}",
                }
                raise RuntimeError(
                    f"polars step '{node.id}' ({step.id}) failed: {e}"
                ) from e
            # Post-step NaN scan + coerce — happens BEFORE we persist the
            # parquet, so the on-disk frame is clean and the sidecar
            # carries the (column, row_indices, cause) record for the UI.
            try:
                origins_payload = _scan_and_coerce_nan(
                    res, run_id=run_id, pipeline_id=p.id,
                    node_id=node.id, step_id=step.id,
                )
            except Exception:
                log.exception("nan-scan failed for node %s — proceeding without sidecar", node.id)
                origins_payload = []
            if origins_payload:
                nan_origins_by_node[node.id] = origins_payload
            intermed_path = intermediate_dir / f"{node.id}.parquet"
            res.output.write_parquet(intermed_path, compression="zstd")
            materialized[node.id] = str(intermed_path)
            # Per-node metrics — Polars path gives us rows_out for free.
            node_metrics[node.id] = {
                "status": "success",
                "rows_out": int(res.output.height),
                "elapsed_ms": int((time.perf_counter() - node_started) * 1000),
            }
            # Hoist any non-output artifacts onto a synthetic key in `artifacts`.
            if res.artifacts:
                artifacts.setdefault(f"_intermediate:{node.id}", []).extend(res.artifacts)

        for o in pipeline_outputs:
            term_started = time.perf_counter()
            path, rc, arts, cols, nan_origins = _run_one_output(
                con, p, o,
                out_dir=out_dir, run_id=run_id, sample_rows=sample_rows,
                materialized=materialized, pipeline_chain=_pipeline_chain,
            )
            outputs[o.id] = path
            row_counts[o.id] = rc
            if arts:
                artifacts[o.id] = arts
            if nan_origins:
                nan_origins_by_node[o.from_.ref] = nan_origins
            # Attach metrics to the terminal node (the one this output is
            # `from_`). This is what the canvas run-state overlay reads
            # AND what the post-run drift detector compares to history.
            node_metrics[o.from_.ref] = {
                "status": "success",
                "rows_out": int(rc) if rc is not None else None,
                "elapsed_ms": int((time.perf_counter() - term_started) * 1000),
                "columns": cols,
            }

        # Mark every non-terminal SQL node as "success" (no row count —
        # we'd have to issue a SELECT count(*) per node to get one). The
        # frontend renders these with the green strip but no row chip;
        # acceptable trade-off vs running N extra count queries.
        terminal_ids = {o.from_.ref for o in pipeline_outputs}
        for n in p.nodes:
            if n.id in node_metrics:
                continue
            if n.id in terminal_ids:
                continue
            node_metrics[n.id] = {"status": "success"}

        # Run per-step NaN-origin queries (SQL-engine steps that turn
        # non-null inputs into NULL outputs — the cast_type pattern).
        # The post-step Polars scanner already covered Polars-engine
        # steps; this loop picks up the SQL side. Best-effort: failure
        # to enumerate failing rows logs but doesn't fail the run.
        for node in topo_sort(p):
            if node.id in nan_origins_by_node:
                # Already covered by the Polars post-step scanner; SQL
                # path would only duplicate.
                continue
            try:
                step = steps().get(node.step)
            except KeyError:
                continue
            inputs_for_node: dict[str, str] = {
                port: quote_ident(ref.ref) for port, ref in node.inputs.items()
            }
            try:
                nan_hook = step.nan_origin_sql(node.params, inputs_for_node)
            except Exception:
                log.exception("nan_origin_sql raised for node %s", node.id)
                continue
            if not nan_hook:
                continue
            source_col, nan_sql = nan_hook
            first_input = next(iter(node.inputs.values()), None)
            if first_input is None:
                continue
            try:
                upstream_sql = compile_to_sql(p, terminal=first_input.ref, overrides=materialized)
            except Exception:
                log.exception("nan-origin upstream compile failed for node %s", node.id)
                continue
            if not upstream_sql.lstrip().upper().startswith("WITH"):
                full_sql = nan_sql
            else:
                marker = " SELECT * FROM "
                idx = upstream_sql.rfind(marker)
                if idx < 0:
                    continue
                with_clause = upstream_sql[: idx + 1]
                full_sql = f"{with_clause}{nan_sql}"
            try:
                rows = con.execute(full_sql).fetchall()
            except Exception:
                log.exception("nan-origin query failed for node %s (sql: %s)", node.id, full_sql[:200])
                continue
            indices = [int(r[0]) for r in rows]
            if not indices:
                continue
            origin = NanOrigin(
                column=source_col,
                row_indices=indices,
                cause="cast_failure",
                source_column=source_col,
            )
            nan_origins_by_node[node.id] = [_nan_origin_to_dict(origin)]
            # Telemetry for SQL-side cast failures — same event kind as
            # the Polars-side scanner emits.
            try:
                import asyncio as _asyncio
                from dig.api.events import EventKinds, emit_event

                async def _emit_one() -> None:
                    await emit_event(
                        EventKinds.DATA_NAN_PRODUCED,
                        run_id=run_id, pipeline_id=p.id,
                        node_id=node.id, step_id=step.id,
                        column=source_col, cause="cast_failure",
                        source_column=source_col, count=len(indices),
                    )

                try:
                    from dig.jobs.manager import main_loop as _main_loop
                    api_loop = _main_loop()
                except Exception:
                    api_loop = None
                if api_loop is not None and api_loop.is_running():
                    _asyncio.run_coroutine_threadsafe(_emit_one(), api_loop)
                else:
                    try:
                        _asyncio.run(_emit_one())
                    except RuntimeError:
                        pass
            except Exception:
                log.exception("cast-failure event emit failed for node %s", node.id)

        # Run per-step validation queries (cast precision, data-quality
        # checks, etc). Each step may opt in by overriding
        # `validation_sql`; we compile the upstream CTE chain for that
        # step's input and append the validation SELECT, then attach
        # the result row as an artifact under a synthetic key. Best-
        # effort — a failed validation logs but doesn't fail the run
        # itself (data-quality events are emitted by the JobManager
        # after the run completes, by inspecting these same artifacts).
        for node in topo_sort(p):
            try:
                step = steps().get(node.step)
            except KeyError:
                continue
            inputs_for_node: dict[str, str] = {
                port: quote_ident(ref.ref) for port, ref in node.inputs.items()
            }
            try:
                vsql = step.validation_sql(node.params, inputs_for_node)
            except Exception:
                log.exception("validation_sql raised for node %s", node.id)
                continue
            if not vsql:
                continue
            # Compile the upstream chain — pick the first input's ref as the
            # terminal CTE the validation reads from.
            first_input = next(iter(node.inputs.values()), None)
            if first_input is None:
                continue
            try:
                upstream_sql = compile_to_sql(p, terminal=first_input.ref, overrides=materialized)
            except Exception:
                log.exception("validation upstream compile failed for node %s", node.id)
                continue
            # Splice: keep only the WITH clause from the upstream compile.
            # compile_to_sql returns "WITH ... SELECT * FROM <terminal>";
            # we need the WITH up to (but not including) the terminal SELECT,
            # then our validation SELECT.
            if not upstream_sql.lstrip().upper().startswith("WITH"):
                # Single-dataset pipeline — wrap in a no-op WITH.
                full_sql = vsql
            else:
                # Find " SELECT * FROM " marker that ends the WITH clause,
                # keep everything up to that point, then append our SELECT.
                marker = " SELECT * FROM "
                idx = upstream_sql.rfind(marker)
                if idx < 0:
                    log.warning("could not splice validation for %s: no SELECT marker", node.id)
                    continue
                with_clause = upstream_sql[: idx + 1]
                full_sql = f"{with_clause}{vsql}"
            try:
                row = con.execute(full_sql).fetchone()
                cols = [d[0] for d in con.description]
                metrics = dict(zip(cols, row))
                clean_metrics = {
                    k: (int(v) if isinstance(v, (int, float)) and v == int(v) else v)
                    for k, v in metrics.items()
                }
                artifacts.setdefault(f"_validation:{node.id}", []).append({
                    "kind": "validation",
                    "label": f"{step.id} validation",
                    "node_id": node.id,
                    "step_id": step.id,
                    "metrics": clean_metrics,
                })
            except Exception:
                log.exception("validation query failed for node %s (sql: %s)", node.id, full_sql[:200])

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ExecutionResult(
            runId=run_id, outputs=outputs, rowCounts=row_counts, elapsedMs=elapsed_ms,
            artifacts=artifacts, nodeMetrics=node_metrics,
            nanOrigins=nan_origins_by_node,
        )
    finally:
        # Always release the in-memory DuckDB connection, even on raise.
        try:
            con.close()
        except Exception:
            log.exception("error closing duckdb connection for run %s", run_id)

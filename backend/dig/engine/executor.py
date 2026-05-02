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
from dig.engine.pipeline import Node, OutputSpec, Pipeline, Reference
from dig.engine.registry import connectors, steps
from dig.engine.step import PolarsContext, Step, quote_ident, quote_str
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


def _ref_alias(ref: Reference) -> str:
    return ref.ref


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
    if spec.connector == "csv":
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
    elif spec.connector == "parquet":
        path = urlparse(spec.uri).path if spec.uri.startswith("file://") else spec.uri
        body = f"SELECT * FROM read_parquet({quote_str(path)})"
    else:
        raise ValueError(f"executor: unsupported connector '{spec.connector}'")

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
) -> tuple[str, int, list[dict[str, Any]]]:
    """Run the pipeline up to this output and write a parquet snapshot.

    Returns (parquet_path, row_count, artifacts).
    """
    terminal = o.from_.ref
    out_path = out_dir / f"{o.name}.parquet"
    artifacts: list[dict[str, Any]] = []
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
            run_id=run_id, out_dir=out_dir, pipeline_chain=pipeline_chain,
        )
        try:
            result = step.execute_polars(input_frames, poly_node.params, ctx)
        except Exception as e:
            raise RuntimeError(f"polars step '{poly_node.id}' ({step.id}) failed: {e}") from e

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

    return str(out_path), row_count, artifacts


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

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're being called from inside a running loop (the JobManager
            # thread offloads execute() via to_thread, so its loop is on the
            # main thread, not here). Build a temp loop for the lookup.
            row = asyncio.run_coroutine_threadsafe(_load(), loop).result()
        else:
            row = asyncio.run(_load())
    except RuntimeError:
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
                run_id=run_id, out_dir=out_dir, pipeline_chain=_pipeline_chain,
            )
            try:
                res = step.execute_polars(input_frames, node.params, ctx)
            except Exception as e:
                raise RuntimeError(
                    f"polars step '{node.id}' ({step.id}) failed: {e}"
                ) from e
            intermed_path = intermediate_dir / f"{node.id}.parquet"
            res.output.write_parquet(intermed_path, compression="zstd")
            materialized[node.id] = str(intermed_path)
            # Hoist any non-output artifacts onto a synthetic key in `artifacts`.
            if res.artifacts:
                artifacts.setdefault(f"_intermediate:{node.id}", []).extend(res.artifacts)

        for o in pipeline_outputs:
            path, rc, arts = _run_one_output(
                con, p, o,
                out_dir=out_dir, run_id=run_id, sample_rows=sample_rows,
                materialized=materialized, pipeline_chain=_pipeline_chain,
            )
            outputs[o.id] = path
            row_counts[o.id] = rc
            if arts:
                artifacts[o.id] = arts

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ExecutionResult(
            runId=run_id, outputs=outputs, rowCounts=row_counts, elapsedMs=elapsed_ms,
            artifacts=artifacts,
        )
    finally:
        # Always release the in-memory DuckDB connection, even on raise.
        try:
            con.close()
        except Exception:
            log.exception("error closing duckdb connection for run %s", run_id)

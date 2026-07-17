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

import hashlib
import inspect
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb

from dig.engine.dag import infer_schemas, topo_sort, validate
from dig.engine.pipeline import Node, OutputSpec, Pipeline, Reference, effective_connector
from dig.engine.registry import connectors, steps
from dig.engine.step import NanOrigin, PolarsContext, PolarsResult, Step, quote_ident, quote_str
from dig.engine.templates import (
    TemplateError,
    build_namespace,
    has_template,
    render_path,
)
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
    # Per-node execution metrics for the canvas run-state overlay.
    # Shape: { node_id: { rows_out?, elapsed_ms?,
    # status: "success"|"failed"|"skipped" } }. Populated for Polars
    # nodes (we have the dataframe) and terminal output nodes (we count
    # the parquet). SQL-only intermediate nodes are marked "success"
    # without row counts — cheap recompute if needed.
    nodeMetrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Per-node NaN-origin sidecars — surfaced by the grid as the
    # orange-⚠ NULL variant on the step that produced the failure.
    # Shape: { node_id: [ {column, row_indices, cause, source_column?}, … ] }.
    # Each entry lives on the producing step ONLY; the next step sees plain
    # NULL because the executor coerces NaN→None after capturing this record.
    nanOrigins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def _ref_alias(ref: Reference) -> str:
    return ref.ref


def _render_pipeline_paths(p: Pipeline, *, run_id: str) -> Pipeline:
    """Resolve `{{ }}` templates in dataset URIs + output sink URIs once per
    run, returning a copy of the pipeline with the rendered values.

    Variables resolve against a frozen-at-run-start namespace
    (see dig.engine.templates.build_namespace) so every node in the run
    sees consistent timestamps and IDs. URI templates that don't contain
    `{{ }}` are passed through unchanged.

    Path safety is enforced — see `assert_path_safe` in templates.py.
    Raises TemplateError on bad references / unsafe paths.
    """
    user_vars = dict(((p.metadata or {}).get("variables")) or {})
    ns = build_namespace(
        run_id=run_id,
        pipeline_id=p.id,
        pipeline_name=p.name,
        user_vars=user_vars,
        env="run",
    )
    # Deep-copy via Pydantic so the original Pipeline (which is often the saved
    # document) is not mutated. The executor sees a separate, rendered copy.
    rendered = p.model_copy(deep=True)
    for d in rendered.datasets:
        if has_template(d.uri):
            d.uri = render_path(d.uri, ns, expand_absolute=True)
    for o in rendered.outputs:
        if o.sink is not None and has_template(o.sink.uri):
            o.sink.uri = render_path(o.sink.uri, ns, expand_absolute=True)
    return rendered


# Cap row-index lists at 10k per (node, column) tuple — keeps the run JSON
# payload bounded. Above the cap we record only the first N indices plus a
# `truncated_count`; the column-header badge still shows the full count.
_NAN_ORIGIN_ROW_CAP = 10_000

# Per-step cap on TOTAL row-index payload across all columns. A wide table
# with 100 float columns each carrying NaN at the row cap would otherwise
# produce 1M indices per step, ballooning the Run.nan_origins JSON column.
# Above this cap, additional columns get count-only entries (row_indices=[],
# truncated=True) so the operator still sees the count in /health and on the
# header chip but the JSON payload stays bounded.
_NAN_ORIGIN_TOTAL_CAP_PER_STEP = 50_000


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
    # Track total payload across all columns this step. Above the cap, we
    # still record per-column counts but stop appending row indices to the
    # JSON sidecar. The grid still shows the chip count; the cells just lose
    # individual orange-⚠ highlighting beyond the cap.
    total_indices_so_far = 0
    for col, dtype in df.schema.items():
        # Float columns and Decimal columns can hold IEEE-style NaN/±Inf.
        # Polars Decimal is a separate dtype; include it so divides-to-NaN
        # in decimal arithmetic don't slip past the scanner.
        is_float = dtype in (pl.Float32, pl.Float64)
        is_decimal = isinstance(dtype, pl.Decimal) if hasattr(pl, "Decimal") else False
        if not (is_float or is_decimal):
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
            # Apply the per-step total cap — beyond the cap, drop row_indices
            # but keep the count so the grid chip + telemetry still see it.
            kept = indices if total_indices_so_far + len(indices) <= _NAN_ORIGIN_TOTAL_CAP_PER_STEP else []
            total_indices_so_far += len(indices)
            new_entries.append(NanOrigin(
                column=col,
                row_indices=kept if kept else [],  # mark count only if dropped
                cause="arithmetic_nan", source_column=None,
            ))
        if inf_mask.any():
            indices = [int(i) for i, v in enumerate(inf_mask.to_list()) if v]
            kept = indices if total_indices_so_far + len(indices) <= _NAN_ORIGIN_TOTAL_CAP_PER_STEP else []
            total_indices_so_far += len(indices)
            new_entries.append(NanOrigin(
                column=col,
                row_indices=kept if kept else [],
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
        # Bump the Prometheus counter — fire-and-forget, never propagates.
        try:
            from dig.observability import inc as _metric_inc

            for origin in result.nan_origins:
                _metric_inc(
                    "dig_nan_cells_produced_total",
                    value=float(len(origin.row_indices)),
                    labels={"cause": origin.cause, "step_id": step_id},
                )
        except Exception:
            log.exception("nan-cell metric increment failed for node %s", node_id)

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
                # Round 8: previously this called ``asyncio.run(_emit_all())``
                # from a worker thread, which spins up a fresh event loop
                # against the main-loop-bound DB engine and intermittently
                # blew up with "loop is closed" / "different loop" errors.
                # When no main loop is captured we skip emission entirely —
                # the metric/log artifact still records the NaN origin, and
                # the alternative (creating a one-shot loop with its own
                # async engine) is more risk than the notification is worth.
                log.debug(
                    "no API loop available; skipping nan-origin event "
                    "emission for node %s",
                    node_id,
                )
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
        # Path is gated by `assert_local_path_safe` BEFORE handing it to DuckDB so
        # a pipeline whose dataset URI was crafted to escape data_dir() (e.g.
        # `file:///etc/passwd`) is rejected, not silently slurped. Round-N
        # finding by the pen tester — the connector layer enforced this gate
        # but the executor's fast-path bypassed it.
        from dig.engine.uri_safety import assert_local_path_safe
        path = str(assert_local_path_safe(spec.uri))
        delim = spec.options.get("delimiter", ",")
        if delim == "\\t":
            delim = "\t"
        header = spec.options.get("header", True)
        body = (
            f"SELECT * FROM read_csv_auto({quote_str(path)}, "
            f"delim={quote_str(delim)}, header={'true' if header else 'false'})"
        )
    elif conn == "parquet":
        from dig.engine.uri_safety import assert_local_path_safe
        path = str(assert_local_path_safe(spec.uri))
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


# Matches DuckDB table-function file reads in a compiled input SQL, so the
# materialization fingerprint can fold in each referenced file's mtime+size.
# Captures the single-quoted path (SQL-escaped '' handled by the caller).
_READ_PATH_RE = re.compile(
    r"read_(?:parquet|csv|csv_auto|json|json_auto|ndjson)\(\s*'((?:[^']|'')*)'",
    re.IGNORECASE,
)


def _fp_for_input_sql(sql: str) -> str:
    """Fingerprint one input port's compiled SQL, folding in the mtime+size of
    every source/intermediate file it reads (read_parquet/read_csv/read_json).

    Because an upstream Polars ancestor is referenced by its parquet path here,
    re-materializing it (which rewrites the parquet, bumping mtime) — or a
    dataset refresh on disk — changes this fingerprint and correctly busts the
    downstream cache.
    """
    parts: list[str] = [sql]
    for raw in sorted(set(_READ_PATH_RE.findall(sql))):
        pth = raw.replace("''", "'")  # un-double SQL-escaped quotes
        try:
            st = os.stat(pth)
            # mtime_ns + size + ctime_ns. ctime (inode change time) is bumped by
            # the kernel on every write and cannot be forged from userspace, so
            # it catches same-size edits that reset mtime (cp -p, rsync --times,
            # tar -x, restore-from-backup) which mtime+size alone would miss.
            parts.append(f"{pth}\x1f{st.st_mtime_ns}\x1f{st.st_size}\x1f{st.st_ctime_ns}")
        except OSError:
            parts.append(f"{pth}\x1fMISSING")
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


def _materialize_fingerprint(
    step_id: str,
    params: dict[str, Any],
    sample_rows: int | None,
    input_sqls: dict[str, str],
    pipeline_variables: dict[str, Any],
) -> str:
    """Content fingerprint for a materialized Polars-ancestor parquet.

    Combines the step id, its params, the row-sample cap, the pipeline
    variables, and a per-input fingerprint of the compiled input SQL. Steps
    receive raw params and render templates internally against the pipeline
    variables (e.g. ``add_runtime_column``), so a variable change with
    unchanged raw params must still bust the cache — hence it's folded in here.
    Two calls whose upstream data, step config, sample size, and variables are
    identical produce the same fingerprint, letting the preview path reuse the
    on-disk parquet instead of re-running ``execute_polars`` on every focus.
    """
    h = hashlib.sha256()
    h.update(step_id.encode())
    h.update(b"\x00")
    h.update(json.dumps(params, sort_keys=True, default=str).encode())
    h.update(b"\x00")
    h.update(json.dumps(pipeline_variables, sort_keys=True, default=str).encode())
    h.update(b"\x00")
    h.update(str(sample_rows).encode())
    for port in sorted(input_sqls):
        h.update(b"\x00")
        h.update(port.encode())
        h.update(b"=")
        h.update(_fp_for_input_sql(input_sqls[port]).encode())
    return h.hexdigest()


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
    # Pipeline variables are pipeline-wide and steps render templates against
    # them, so they participate in every node's fingerprint.
    pipeline_vars = dict(((p.metadata or {}).get("variables")) or {})
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
        # Compile each input port's SQL once (used for both the cache
        # fingerprint and, on a miss, the actual materialization). Building
        # SQL with the running `materialized` dict keeps chains-of-polars
        # correct — an upstream Polars parquet is referenced by path here.
        up_sqls: dict[str, str] = {}
        for port, ref in node.inputs.items():
            up_sql = compile_to_sql(p, terminal=ref.ref, overrides=materialized)
            if sample_rows:
                up_sql = f"{up_sql} LIMIT {int(sample_rows)}"
            up_sqls[port] = up_sql

        # Fingerprint the work: step + params + sample size + variables + a
        # fingerprint of each input SQL (which folds in the mtime/size/ctime of
        # every source file it reads, and — because an upstream Polars ancestor
        # is referenced by its own fingerprint-named parquet — any upstream
        # change too). The fingerprint is baked into the parquet filename, so
        # distinct inputs get distinct files: a warm re-focus of an unchanged
        # chain reuses the exact file instead of re-running the Polars step.
        # Any valid materialization of the same inputs is interchangeable, so
        # concurrent previews racing on the same path are safe. Stale files from
        # earlier edits are harmless and cleared by the boot sweep.
        #
        # Steps that declare ``engine.deterministic: false`` (e.g.
        # add_runtime_column with ``{{ now }}``) legitimately produce different
        # output each call, so they are never reused — they always re-execute
        # and overwrite a single stable file in place (no cache, no growth).
        deterministic = bool(step.manifest.get("engine", {}).get("deterministic", True))
        if deterministic:
            node_fp = _materialize_fingerprint(
                step.id, node.params, sample_rows, up_sqls, pipeline_vars
            )
            intermed_path = out_dir / f"{node.id}.{node_fp[:32]}.parquet"
            if intermed_path.exists():
                materialized[node.id] = str(intermed_path)
                continue
        else:
            intermed_path = out_dir / f"{node.id}.nondet.parquet"

        # Cache miss — materialise this Polars ancestor. SQL inputs are built
        # using the running `materialized` dict so chains-of-polars work.
        input_frames: dict[str, pl.DataFrame] = {}
        for port, up_sql in up_sqls.items():
            input_frames[port] = _materialize_sql_to_polars(con, up_sql)
        from dig.engine.step import PolarsContext  # local: avoid module cycle
        ctx = PolarsContext(
            run_id=run_id, out_dir=out_dir, node_id=node.id, pipeline_chain=pipeline_chain,
            pipeline_id=p.id, pipeline_name=p.name,
            pipeline_variables=dict(((p.metadata or {}).get("variables")) or {}),
        )
        try:
            res = step.execute_polars(input_frames, node.params, ctx)
        except Exception as e:
            raise RuntimeError(
                f"polars step '{node.id}' ({step.id}) failed during preview: {e}"
            ) from e
        # Write to a unique tmp name, then atomically rename onto the
        # fingerprinted path — previews share data/outputs/__preview/<pid>/, so
        # a concurrent preview of the same pipeline must never read a
        # half-written parquet. os.replace is atomic on POSIX; readers
        # (compile_to_sql overrides) see the file whole or not at all.
        tmp_path = out_dir / f".{node.id}.{uuid.uuid4().hex}.tmp.parquet"
        try:
            res.output.write_parquet(tmp_path, compression="zstd")
            os.replace(tmp_path, intermed_path)
        finally:
            tmp_path.unlink(missing_ok=True)
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
            pipeline_id=p.id, pipeline_name=p.name,
            pipeline_variables=dict(((p.metadata or {}).get("variables")) or {}),
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

    # Resolve `{{ }}` templates in dataset URIs + sink URIs once, against a
    # per-run namespace. See dig.engine.templates and docs/VARIABLES.md.
    try:
        p = _render_pipeline_paths(p, run_id=run_id)
    except TemplateError as te:
        raise RuntimeError(f"pipeline template render failed: {te}") from te

    out_dir = data_dir() / "outputs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(database=":memory:")
    outputs: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    artifacts: dict[str, list[dict[str, Any]]] = {}
    # Per-node metrics for the canvas run-state overlay. Keyed by node id;
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
                pipeline_id=p.id, pipeline_name=p.name,
                pipeline_variables=dict(((p.metadata or {}).get("variables")) or {}),
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
                # Round-9 fix: previous form crashed on NaN/Inf
                # (`int(NaN)`/`int(inf)` raise ValueError) and silently
                # coerced booleans to 0/1 because ``bool`` is a subclass
                # of ``int``. Skip non-finite floats and exclude bool
                # explicitly so a `passed=True` column stays True.
                import math as _math
                def _coerce(v: Any) -> Any:
                    if isinstance(v, bool):
                        return v
                    if isinstance(v, (int, float)) and _math.isfinite(v) and v == int(v):
                        return int(v)
                    return v
                clean_metrics = {k: _coerce(v) for k, v in metrics.items()}
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

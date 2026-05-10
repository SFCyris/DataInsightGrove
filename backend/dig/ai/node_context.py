"""Build the AI features' context for a focused node — works the same
whether the focused thing is a registered dataset or any step output.

The three "Hints panel" AI features (explain_dataset, suggest_pipeline_steps,
suggest_visualizations) all need the same five inputs:

  1. **Schema** at the focused node — column names + types
  2. **Sample values** — top-N values per column from the actual rows
     the user is looking at (NOT upstream — for derived nodes the
     samples must reflect the post-transform output)
  3. **Source URI + connector** of the underlying dataset for
     domain-inference signals (filenames, JDBC URLs etc.)
  4. **Project / pipeline name** (operator-supplied label)
  5. **Applied steps** — for derived nodes, the chain of step labels +
     params from the dataset to the focused node so the LLM can frame
     "given the original dataset and these steps, what's left?"

This module gathers all five with a single entry point:

    ctx = await build_ai_node_context(session, pipeline_id, node_id)

When ``node_id`` is None (or refers to a dataset), behaves like the
old dataset-only path. When it's a step id, samples are pulled from
the focused step's output via the same compile + sampling + execute
path the live grid uses (`preview-step-rows` semantics) — using the
pipeline's currently-selected sampling method.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AiNodeContext:
    """All the context any of the three AI features needs."""
    # Display labels
    project_name: str = ""
    dataset_name: str = ""
    # Schema at the focused node — column → type
    schema: dict[str, str] = field(default_factory=dict)
    # Top-N samples per column at the focused node
    sample_values: dict[str, list[str]] = field(default_factory=dict)
    # Domain-hint signals (always sourced from the underlying dataset,
    # since e.g. filename is what tells the LLM the data came from a
    # clinical trial vs an e-commerce export)
    source_uri: str | None = None
    connector: str | None = None
    # Empty list when focused on a dataset; populated when focused on
    # a step. Each entry is a short human-readable phrase like
    # "Group by category and channel summing total_revenue" — built
    # from the manifest label + key params, not raw step IDs.
    applied_steps: list[str] = field(default_factory=list)
    # Whether the focused thing is a derived step (vs a raw dataset).
    # Drives prompt phrasing in explain_dataset.
    is_derived: bool = False


async def build_ai_node_context(
    session: AsyncSession,
    pipeline_id: str,
    node_id: str | None,
    *,
    top_n_per_col: int = 3,
    sample_cap: int = 5_000,
) -> AiNodeContext:
    """Gather the five inputs above for a focused node or dataset.

    `node_id`:
      - None or a registered dataset id → dataset-only path; samples
        come from the cached profile (cheap, no execution).
      - A step id → derived path; samples come from running the step's
        output through the pipeline's chosen sampling method.

    `sample_cap` upper-bounds how many rows we ask the engine to
    materialize before harvesting top-N. The pipeline's metadata-level
    sampling config already constrains this; the cap is a defensive
    ceiling for huge derived outputs.
    """
    from dig.api.pipelines import PipelineRow
    from dig.engine.dag import infer_schemas
    from dig.engine.pipeline import Pipeline
    from dig.engine.pipeline_step_inline import inline_sub_pipelines
    from dig.storage.models import Dataset as DatasetRow
    from sqlalchemy import select as sa_select

    ctx = AiNodeContext()

    prow = await session.get(PipelineRow, pipeline_id)
    if prow is None:
        raise ValueError(f"pipeline {pipeline_id!r} not found")
    doc = prow.document or {}
    ctx.project_name = doc.get("name") or ""

    # Inline sub-pipelines so a step published as a sub-pipeline still
    # resolves when we walk the chain.
    flat_doc = await inline_sub_pipelines(session, doc)
    p = Pipeline.model_validate(flat_doc)

    # Resolve which dataset is the upstream root for this node — the
    # dataset whose source URI / connector is the domain-hint source.
    # For multi-input nodes (joins) we pick the first dataset reached
    # in BFS; the AI feature gets one provenance hint, not several.
    upstream_alias = _root_dataset_for_node(p, node_id) if node_id else None
    if upstream_alias is None and p.datasets:
        upstream_alias = p.datasets[0].id

    # Translate the pipeline-doc dataset alias (e.g. "ds_main") to the
    # registered DatasetRow id. The alias may BE the row id (legacy
    # convention `ds_<ULID_lower>`), or the alias may be arbitrary
    # (e.g. "ds_main") with the row id embedded in the alias's
    # cached-parquet URI. Mirrors the frontend's `focusedDatasetReal`
    # logic so the same lookup works for any pipeline shape.
    ds_row = None
    if upstream_alias:
        upstream_spec = next((d for d in p.datasets if d.id == upstream_alias), None)
        candidate_ids: list[str] = [upstream_alias]
        # Some pipelines use `ds_<ULID_lower>` aliases — strip the
        # prefix and uppercase. Either is a hit.
        if upstream_alias.lower().startswith("ds_") and len(upstream_alias) > 3:
            candidate_ids.append(upstream_alias[3:].upper())
        if upstream_spec is not None and upstream_spec.uri:
            import re as _re
            m = _re.search(r"([0-9A-Za-z]{26})\.parquet", upstream_spec.uri)
            if m:
                candidate_ids.append(m.group(1).upper())
        for cid in candidate_ids:
            ds_row = (await session.execute(
                sa_select(DatasetRow).where(DatasetRow.id == cid),
            )).scalar_one_or_none()
            if ds_row is not None:
                break
        if ds_row is not None:
            ctx.dataset_name = ds_row.name or ""
            ctx.source_uri = ds_row.source_uri or None
            ctx.connector = ds_row.connector or None
        elif upstream_spec is not None:
            # Fall back to the pipeline-doc spec's hints — no row in
            # the DB but we can still tell the LLM "this came from <uri>".
            ctx.dataset_name = upstream_spec.label or upstream_alias
            ctx.source_uri = upstream_spec.uri or None
            ctx.connector = upstream_spec.connector or None
    upstream_dataset_id = ds_row.id if ds_row is not None else upstream_alias

    # Schema at focused node — `infer_schemas` returns a dict keyed by
    # ref id (dataset.id or node.id), so the same lookup works for both.
    target_id = node_id or upstream_dataset_id
    if target_id is None:
        return ctx

    # Determine whether this id refers to a step (vs a dataset).
    is_node = any(n.id == target_id for n in p.nodes)
    ctx.is_derived = is_node

    if not is_node:
        # Dataset-only path: schema + samples come from the cached
        # profile. Same as the legacy dataset-focused behavior — keeps
        # latency at zero extra queries when the user is on a dataset.
        if upstream_dataset_id and ds_row is not None:
            ctx.schema = {c["name"]: c.get("type", "string") for c in (ds_row.columns or [])}
            ctx.sample_values = _top_values_from_profile(ds_row.columns or [], top_n_per_col)
        return ctx

    # Derived-node path: schema is computed; samples come from running
    # the focused step's output through the pipeline's chosen sampling.
    schemas = await asyncio.to_thread(infer_schemas, p)
    ctx.schema = dict(schemas.get(target_id, {}))
    ctx.sample_values = await _harvest_node_samples(
        flat_doc, target_id,
        top_n_per_col=top_n_per_col,
        sample_cap=sample_cap,
    )
    ctx.applied_steps = _build_applied_steps(p, target_id)
    return ctx


# ── Helpers ──────────────────────────────────────────────────────────


def _root_dataset_for_node(p: "Any", node_id: str) -> str | None:
    """BFS upward from `node_id` to the first dataset id reached.

    Used for domain-hint sourcing — the dataset's filename / connector
    is more telling than any intermediate step's, so we walk back to
    the root of the focused branch. Only walks the first input port at
    each step (good enough for hint sourcing; we're not attributing
    multi-source semantics).
    """
    nodes_by_id = {n.id: n for n in p.nodes}
    dataset_ids = {d.id for d in p.datasets}
    visited: set[str] = set()
    queue = [node_id]
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        if cur in dataset_ids:
            return cur
        node = nodes_by_id.get(cur)
        if node is None:
            continue
        for ref in node.inputs.values():
            if ref.ref not in visited:
                queue.append(ref.ref)
    return None


def _top_values_from_profile(columns: list[dict], top_n: int) -> dict[str, list[str]]:
    """Extract top-N value strings from a cached column profile.

    The profile's top-values shape varies (legacy `top_values`, current
    `topValues`, sometimes a list of dicts with `value`, sometimes a
    list of bare strings). Tolerates all of them.
    """
    out: dict[str, list[str]] = {}
    for c in columns:
        top = c.get("topValues") or c.get("top_values") or []
        vals: list[str] = []
        for item in top[:top_n]:
            if isinstance(item, dict):
                v = item.get("value")
                if v is not None:
                    vals.append(str(v))
            elif item is not None:
                vals.append(str(item))
        if vals:
            out[c["name"]] = vals
    return out


def _build_applied_steps(p: "Any", target_node_id: str) -> list[str]:
    """Walk dataset → ... → target_node, returning a short text per
    step. Each entry reads like:

        Group rows · groupBy=category, channel
        Sort rows · keys=week_start asc, total_revenue desc
        Filter rows · channel = 'organic'

    The phrasing is deterministic — no LLM cost. Used as context for
    the explainer prompt so it can frame "of the original dataset and
    the applied steps, what's left and what does it represent?".
    """
    nodes_by_id = {n.id: n for n in p.nodes}

    # Build the linear chain back from target_node_id by following the
    # first input ref at each hop. Stops when we hit a dataset.
    chain: list[str] = []
    cur: str | None = target_node_id
    visited: set[str] = set()
    while cur is not None and cur in nodes_by_id and cur not in visited:
        visited.add(cur)
        node = nodes_by_id[cur]
        label = (node.ui.label if node.ui and node.ui.label else None) or node.step
        params_str = _summarize_params(node.params or {})
        chain.append(f"{label}{(' · ' + params_str) if params_str else ''}")
        # Walk back via first input port.
        nxt = None
        for ref in node.inputs.values():
            nxt = ref.ref
            break
        cur = nxt
    return list(reversed(chain))


def _summarize_params(params: dict[str, Any]) -> str:
    """Compact, readable param summary for the chain text. Caps each
    value at ~40 chars and the overall summary at ~120 chars."""
    if not params:
        return ""
    parts: list[str] = []
    for k, v in params.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        if isinstance(v, list):
            shown = ", ".join(str(x) for x in v[:3])
            if len(v) > 3:
                shown += f", +{len(v) - 3}"
            parts.append(f"{k}=[{shown}]")
        elif isinstance(v, dict):
            # Single-level dict summary (groupBy={col: 'sum'}, etc.).
            inner = ", ".join(f"{ik}={iv}" for ik, iv in list(v.items())[:3])
            parts.append(f"{k}={{{inner}}}")
        else:
            s = str(v)
            if len(s) > 40:
                s = s[:37] + "..."
            parts.append(f"{k}={s}")
    summary = "; ".join(parts)
    if len(summary) > 120:
        summary = summary[:117] + "..."
    return summary


async def _harvest_node_samples(
    flat_doc: dict[str, Any],
    target_node_id: str,
    *,
    top_n_per_col: int,
    sample_cap: int,
) -> dict[str, list[str]]:
    """Run the focused node's output through the pipeline's chosen
    sampling method, then collect top-N values per column.

    Reuses the same compile + sample + materialize path as
    `preview-step-rows`. Samples honor `metadata.sampling` (head /
    tail / random / systematic) so any new sampling method added to
    `dig.engine.sampling` is picked up automatically.
    """
    from dig.engine.executor import (
        compile_to_sql,
        materialize_polars_ancestors,
        _terminal_polars_node,
        _materialize_sql_to_polars,
    )
    from dig.engine.pipeline import Pipeline
    from dig.engine.sampling import SamplingConfig, wrap_with_sampling
    from dig.engine.step import PolarsContext
    from dig.storage.files import data_dir as _data_dir

    p = Pipeline.model_validate(flat_doc)

    sampling_cfg = SamplingConfig.from_metadata(
        (flat_doc.get("metadata") or {}).get("sampling")
    )
    if sampling_cfg is None:
        # No pipeline-level sampling chosen → cap at sample_cap with head.
        sampling_cfg = SamplingConfig(method="head", size=sample_cap)

    poly_node = _terminal_polars_node(p, target_node_id)
    is_sql = poly_node is None
    pipeline_id = flat_doc.get("id") or "unknown"
    preview_dir = _data_dir() / "outputs" / "__ai_samples" / pipeline_id

    def _run() -> dict[str, list[str]]:
        import duckdb
        con = duckdb.connect(database=":memory:")
        try:
            materialized = materialize_polars_ancestors(
                con, p, target_node_id,
                out_dir=preview_dir, sample_rows=sample_cap,
            )
            if is_sql:
                sql = compile_to_sql(p, terminal=target_node_id, overrides=materialized)
                sql = wrap_with_sampling(sql, sampling_cfg)
                df = con.execute(sql).pl()
            else:
                # Polars terminal — same shape as preview-step-rows: feed
                # each input via sampled SQL, then run execute_polars.
                assert poly_node is not None
                from dig.engine.registry import steps as _steps
                step = _steps().get(poly_node.step)
                input_frames: dict[str, Any] = {}
                for port, ref in poly_node.inputs.items():
                    up_sql = compile_to_sql(p, terminal=ref.ref, overrides=materialized)
                    up_sql = wrap_with_sampling(up_sql, sampling_cfg)
                    input_frames[port] = _materialize_sql_to_polars(con, up_sql)
                ctx_p = PolarsContext(
                    run_id="__ai_samples",
                    out_dir=preview_dir,
                    node_id=poly_node.id,
                )
                df = step.execute_polars(input_frames, poly_node.params, ctx_p).output
        finally:
            con.close()

        return _polars_top_n(df, top_n_per_col)

    return await asyncio.to_thread(_run)


def _polars_top_n(df: "Any", top_n: int) -> dict[str, list[str]]:
    """Per-column top-N by frequency. Strings via str() so the AI
    prompt sees clean text regardless of pl.Datetime, pl.Decimal etc."""
    out: dict[str, list[str]] = {}
    if df is None or df.height == 0:
        return out
    for col in df.columns:
        try:
            vc = df.get_column(col).value_counts(sort=True).head(top_n)
            # value_counts returns columns named by the source column
            # plus "count"; pull the value column by name.
            vals = vc.get_column(col).to_list()
        except Exception:
            # Any column type that doesn't support value_counts (e.g.
            # nested struct) — skip; the AI is fine without samples
            # for those.
            continue
        clean = [str(v) for v in vals if v is not None]
        if clean:
            out[col] = clean
    return out

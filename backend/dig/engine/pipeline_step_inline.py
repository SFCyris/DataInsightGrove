"""Inline-expansion of pipeline-step references.

Walks a parent pipeline document; for every node whose ``step`` is
``pipeline:<id>``, fetches the pinned source document and splices its
nodes into the parent in place of the reference. The result is a
flat document — by the time validate / topo-sort / compile see it,
there are no nested pipelines.

Why splice rather than nest at runtime?

  * Lineage and per-row tracing want a flat node id space — a nested
    runtime would force every consumer (executor, lineage UI, run
    history) to learn about node-id namespacing.
  * The DuckDB-WASM compiler emits CTEs keyed by node id; with flat
    ids the existing compile pipeline works unchanged.
  * Cycle detection is already enforced at save time (see
    ``pipeline_step.check_no_cycle``) so the inliner doesn't need to
    re-prove non-cycle.

MVP shape (single-input, single-output): the source pipeline must
declare exactly one dataset (the input slot, alias ``main``) and
the sub-pipeline node's ``inputs.main.ref`` is rewired to point to
the upstream of the consumer node. The terminal of the source
pipeline (last node by topological order) becomes the output of
the spliced step — the consumer's ``outputs[0]`` ref is rewritten
to that node id.
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from dig.engine.pipeline_step import (
    fetch_pinned_document,
    is_pipeline_step,
    source_pipeline_id,
    collect_exposed_params,
    published_as_step,
)


def _prefix_id(prefix: str, raw_id: str) -> str:
    """Namespace a child node id under a per-instance prefix.

    The prefix is the parent's wrapper-node id so multiple instances
    of the same sub-pipeline don't collide. Result format:
    ``<parent_node_id>__<child_node_id>``.
    """
    return f"{prefix}__{raw_id}"


def _rewrite_refs(node: dict[str, Any], remap: dict[str, str]) -> dict[str, Any]:
    """Return a copy of ``node`` with every ``ref`` field rewritten via
    ``remap``. Entries not in ``remap`` are left as-is so the function
    is safe to call when only some refs need namespacing.
    """
    n = copy.deepcopy(node)
    inputs = n.get("inputs") or {}
    new_inputs: dict[str, Any] = {}
    for slot, ref in inputs.items():
        if isinstance(ref, dict) and "ref" in ref:
            target = ref["ref"]
            new_inputs[slot] = {**ref, "ref": remap.get(target, target)}
        else:
            new_inputs[slot] = ref
    n["inputs"] = new_inputs
    return n


def _expand_one(
    parent_node: dict[str, Any],
    source_doc: dict[str, Any],
    consumer_alias_to_ref: dict[str, str],
    consumer_param_overrides: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Return ``(spliced_nodes, terminal_node_id)`` for one inlining.

    The returned ``terminal_node_id`` is what the parent pipeline's
    downstream nodes should read from in place of ``parent_node['id']``.
    """
    parent_id = parent_node["id"]
    src_datasets = source_doc.get("datasets") or []
    src_nodes = source_doc.get("nodes") or []
    if not src_datasets:
        raise ValueError(
            f"sub-pipeline source has no datasets — can't be used as a step"
        )
    if not src_nodes:
        raise ValueError(
            f"sub-pipeline source has no transformation steps — can't be used as a step"
        )

    # MVP: single-input. The lone dataset is the implicit "main" input.
    sole_dataset_id = src_datasets[0]["id"]

    # Build the id remap: every child node id gets prefixed; the lone
    # dataset id maps to the consumer's upstream ref.
    id_remap: dict[str, str] = {}
    upstream_ref = consumer_alias_to_ref.get("main")
    if upstream_ref is None:
        # Fallback: if the consumer didn't wire a "main" input, use the
        # first input slot. This shouldn't normally happen because the
        # synthesized manifest declares "main" as the only input.
        first_input = next(iter((parent_node.get("inputs") or {}).values()), None)
        if isinstance(first_input, dict):
            upstream_ref = first_input.get("ref")
    if upstream_ref is None:
        raise ValueError(
            f"sub-pipeline node {parent_id!r} has no input wired"
        )
    id_remap[sole_dataset_id] = upstream_ref

    for n in src_nodes:
        id_remap[n["id"]] = _prefix_id(parent_id, n["id"])

    # Apply the consumer's exposed-param overrides to the matching
    # child nodes. The exposed-params metadata lives on the child
    # nodes themselves under ui.exposedParams.
    exposed = collect_exposed_params(source_doc)
    overrides_by_node: dict[str, dict[str, Any]] = {}
    for ep in exposed:
        alias = ep["alias"]
        if alias in consumer_param_overrides:
            overrides_by_node.setdefault(ep["nodeId"], {})[ep["paramKey"]] = (
                consumer_param_overrides[alias]
            )

    spliced: list[dict[str, Any]] = []
    last_node_id: str | None = None
    for n in src_nodes:
        rewritten = _rewrite_refs(n, id_remap)
        rewritten["id"] = id_remap[n["id"]]
        # Apply param overrides for this node, if any.
        ovr = overrides_by_node.get(n["id"])
        if ovr:
            rewritten["params"] = {**(rewritten.get("params") or {}), **ovr}
        spliced.append(rewritten)
        last_node_id = rewritten["id"]

    if last_node_id is None:
        raise ValueError("sub-pipeline produced no nodes after splicing")
    return spliced, last_node_id


async def inline_sub_pipelines(
    session: AsyncSession,
    parent_doc: dict[str, Any],
) -> dict[str, Any]:
    """Return a flattened copy of ``parent_doc``: every node whose step
    is ``pipeline:<id>`` is replaced by the spliced contents of the
    pinned source pipeline.

    Cheap no-op when the parent doesn't reference any sub-pipelines.
    """
    nodes = parent_doc.get("nodes") or []
    if not any(isinstance(n.get("step"), str) and is_pipeline_step(n["step"]) for n in nodes):
        return parent_doc  # fast-path

    flat = copy.deepcopy(parent_doc)
    out_nodes: list[dict[str, Any]] = []

    for n in flat["nodes"]:
        sid = n.get("step")
        if not (isinstance(sid, str) and is_pipeline_step(sid)):
            out_nodes.append(n)
            continue
        src_pid = source_pipeline_id(sid)
        params = n.get("params") or {}
        pinned_etag = int(params.get("pinnedEtag") or 1)
        try:
            src_doc = await fetch_pinned_document(session, src_pid, pinned_etag)
        except ValueError as e:
            raise ValueError(f"node {n['id']!r}: {e}") from e
        if published_as_step(src_doc) is None:
            raise ValueError(
                f"node {n['id']!r}: source pipeline {src_pid!r} is no longer "
                "published as a step. Re-publish it on the source side, "
                "or remove this node."
            )
        # Build alias-to-ref map. The consumer's `inputs` dict is keyed
        # by alias names (just "main" in the MVP).
        alias_to_ref: dict[str, str] = {}
        for slot, ref in (n.get("inputs") or {}).items():
            if isinstance(ref, dict) and "ref" in ref:
                alias_to_ref[slot] = ref["ref"]
        # The consumer's params are keyed by alias for exposed params,
        # plus the system `pinnedEtag` which we drop.
        param_overrides = {k: v for k, v in params.items() if k != "pinnedEtag"}
        spliced_nodes, terminal_id = _expand_one(
            n, src_doc, alias_to_ref, param_overrides,
        )
        out_nodes.extend(spliced_nodes)
        # Replace the wrapper node with a passthrough that keeps the
        # wrapper id alive. The inliner's downstream invariant is:
        # any node id that existed in the parent doc still exists in
        # the flat doc. That preserves compile terminal-selection,
        # downstream wiring, and per-row lineage handles.
        out_nodes.append({
            "id": n["id"],
            "step": "passthrough",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": terminal_id, "port": "out"}},
            "outputs": ["out"],
            "params": {},
            "ui": n.get("ui") or {},
        })

    flat["nodes"] = out_nodes
    return flat

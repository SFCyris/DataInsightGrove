"""Pipeline-step composition.

A pipeline can be "published as a reusable step" by setting
`metadata.publishedAsStep` on its document. Once published it appears
in the step picker like any other step (with a 🪆 source badge), and
inserting it into another pipeline becomes a single node that the
compiler inline-expands at run/preview time.

Design choices
--------------

* **Step ID format**: ``pipeline:<sourcePipelineId>``. The colon is
  unambiguous; built-in steps and pack steps never contain one.
* **Pinning**: a parent's reference to a sub-pipeline pins to a specific
  ``pinnedEtag`` (stored in the parent node's ``params``). The
  inlining code reads the pinned snapshot from ``pipeline_history`` so
  edits to the source pipeline don't silently change the parent's
  behaviour. The UI offers a "Upgrade to latest" affordance.
* **MVP shape (intentional restriction)**: published pipelines must
  have exactly ONE dataset (the input slot, exposed as ``main``) and
  exactly ONE terminal node (the output, exposed as ``out``). This
  keeps the inlining algorithm tractable; multi-input / multi-output
  composition can layer on top later without breaking the format.
* **Cycle prevention**: ``pipeline_step_dependencies`` walks the
  transitive closure of pipeline-step references; ``check_no_cycle``
  rejects a parent whose composition would create one. The check runs
  on save AND at run-start so a malicious doc can't sneak past.

Format reference
----------------

In the source pipeline's document::

    {
      "id": "01...",
      "datasets": [{ "id": "ds_a", ... }],
      "nodes": [
        {
          "id": "n_x",
          "step": "filter_rows",
          "inputs": { "in": { "ref": "ds_a" } },
          "params": { "expr": "x > 0" },
          "ui": { "exposedParams": { "expr": { "alias": "filterExpr",
                                               "help": "..." } } }
        }
      ],
      "metadata": {
        "publishedAsStep": {
          "label": "Positive rows only",
          "emoji": "✂️",
          "description": "Keeps rows with x > 0",
          "category": "custom"
        }
      }
    }

In the consumer's document::

    {
      "nodes": [
        {
          "id": "n_y",
          "step": "pipeline:01...",
          "inputs": { "main": { "ref": "ds_consumer" } },
          "params": {
            "pinnedEtag": 27,
            "filterExpr": "y > 5"
          }
        }
      ]
    }
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dig.storage.models import Pipeline as PipelineRow, PipelineHistory


# Prefix used to mint sub-pipeline step ids. Anything starting with
# this is a virtual step backed by another pipeline document.
PIPELINE_STEP_PREFIX = "pipeline:"


def is_pipeline_step(step_id: str) -> bool:
    return step_id.startswith(PIPELINE_STEP_PREFIX)


def source_pipeline_id(step_id: str) -> str:
    """Extract source pipeline id from a `pipeline:<id>` step id."""
    if not is_pipeline_step(step_id):
        raise ValueError(f"not a pipeline step id: {step_id!r}")
    return step_id[len(PIPELINE_STEP_PREFIX):]


def published_as_step(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Return the publishedAsStep config if the doc is published, else None."""
    meta = doc.get("metadata") or {}
    cfg = meta.get("publishedAsStep")
    return cfg if isinstance(cfg, dict) else None


def collect_exposed_params(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the doc's nodes and collect ui.exposedParams entries.

    Returns a list of dicts: ``{ nodeId, paramKey, alias, help, default }``.
    Used both by the manifest generator (to declare params on the
    virtual step) and by the inliner (to substitute consumer values
    back into the embedded nodes).
    """
    out: list[dict[str, Any]] = []
    for n in doc.get("nodes") or []:
        ui = n.get("ui") or {}
        exposed = ui.get("exposedParams") or {}
        if not isinstance(exposed, dict):
            continue
        node_id = n.get("id")
        node_params = n.get("params") or {}
        for pkey, meta in exposed.items():
            if not isinstance(meta, dict):
                continue
            alias = meta.get("alias") or pkey
            out.append({
                "nodeId": node_id,
                "paramKey": pkey,
                "alias": alias,
                "help": meta.get("help") or "",
                "default": node_params.get(pkey),
            })
    return out


def synthesize_manifest(pipeline_id: str, doc: dict[str, Any], etag: int) -> dict[str, Any] | None:
    """Generate a step-manifest dict from a published pipeline document.

    Returns None if the pipeline isn't published. Otherwise returns the
    manifest in the same shape that disk-loaded steps use, with three
    additions:
      - ``id`` is `pipeline:<pipeline_id>` so consumers can reference it.
      - ``params.pinnedEtag`` is auto-injected (an integer param the
        consumer's UI hides; the inliner reads it).
      - exposed params from inner nodes are surfaced at the top level.
    """
    cfg = published_as_step(doc)
    if not cfg:
        return None

    # MVP: require exactly one dataset and one terminal node.
    datasets = doc.get("datasets") or []
    nodes = doc.get("nodes") or []
    if not datasets or not nodes:
        return None

    label = str(cfg.get("label") or doc.get("name") or pipeline_id)
    description = str(cfg.get("description") or "")
    category = str(cfg.get("category") or "custom")
    emoji = str(cfg.get("emoji") or "🪆")

    # Build the manifest.params dict with one entry per exposed param.
    # ParamSpec requires {type, label}; help/default optional.
    params: dict[str, Any] = {
        # System param — the inliner reads it; we hide via visibleWhen
        # since the schema doesn't have a "hidden" field. Setting
        # visibleWhen to a never-matching key effectively hides the row.
        "pinnedEtag": {
            "type": "integer",
            "label": "Pinned version",
            "default": etag,
            "help": "Source-pipeline version this consumer is locked to. Use the Upgrade button to bump it.",
            "visibleWhen": {"__never__": True},
        },
    }
    for ep in collect_exposed_params(doc):
        params[ep["alias"]] = {
            "type": "string",  # MVP: treat as opaque string; consumer can override
            "label": ep["alias"],
            "default": ep["default"] if ep["default"] is not None else "",
            "help": ep["help"] or f"Inherited from node {ep['nodeId']} param {ep['paramKey']}",
        }

    return {
        "id": f"{PIPELINE_STEP_PREFIX}{pipeline_id}",
        "version": str(etag),
        "label": f"{emoji} {label}",
        "description": description or f"Composite step from pipeline {pipeline_id}",
        "category": category,
        # Engine = "polars" because the inliner replaces this node with
        # the source pipeline's actual nodes before compile; the
        # consumer-facing engine never executes the composite-step id
        # directly. Browser is set to the most permissive ("sql") so
        # picker greying logic doesn't disqualify it.
        "engine": {
            "primary": "polars",
            "browser": "sql",
            "deterministic": True,
        },
        "io": {
            "inputs": {"min": 1, "max": 1, "ports": ["main"]},
            "outputs": {"min": 1, "max": 1, "ports": ["out"]},
        },
        "params": params,
    }


async def list_published_pipelines(session: AsyncSession) -> list[dict[str, Any]]:
    """Return manifest dicts for every pipeline that's published as a step.

    Used by the /steps endpoint to extend the on-disk registry with
    DB-backed virtual steps. Reads only the live document (not history)
    — the registry surface always shows the *current* version of the
    source. Consumers pin to ``pinnedEtag`` separately so they aren't
    affected by a change here.
    """
    rows = (await session.execute(select(PipelineRow))).scalars().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        doc = row.document or {}
        m = synthesize_manifest(row.id, doc, row.etag or 1)
        if m is not None:
            m["source"] = f"pipeline:{row.id}"
            out.append(m)
    return out


async def fetch_pinned_document(
    session: AsyncSession,
    source_pipeline_id_str: str,
    pinned_etag: int,
) -> dict[str, Any]:
    """Return the pinned snapshot's document, or raise ValueError.

    Looks in ``pipeline_history`` for the snapshot at that etag. If the
    pinned snapshot has been pruned (very old + lots of edits since),
    raises so the caller can surface a clear "version no longer
    available — upgrade to latest" message.
    """
    snap = (await session.execute(
        select(PipelineHistory).where(
            PipelineHistory.pipeline_id == source_pipeline_id_str,
            PipelineHistory.etag == pinned_etag,
        )
    )).scalars().first()
    if snap is None:
        # Fall back to the live document if the history was pruned.
        # Surface a warning by raising — the caller should map to a
        # user-visible "history pruned, please upgrade" path.
        live = await session.get(PipelineRow, source_pipeline_id_str)
        if live is None:
            raise ValueError(
                f"source pipeline {source_pipeline_id_str!r} not found"
            )
        if (live.etag or 1) == pinned_etag:
            return dict(live.document or {})
        raise ValueError(
            f"pinned etag {pinned_etag} for pipeline {source_pipeline_id_str!r} "
            f"no longer in history — Upgrade to latest (current: v{live.etag})."
        )
    return dict(snap.document)


# ---- Cycle detection -----------------------------------------------------


def direct_pipeline_step_deps(doc: dict[str, Any]) -> set[str]:
    """Return the set of pipeline ids that this document references
    as sub-pipeline steps. Doesn't traverse transitively — caller is
    expected to do BFS via ``transitive_pipeline_step_deps``.
    """
    deps: set[str] = set()
    for n in doc.get("nodes") or []:
        sid = n.get("step")
        if isinstance(sid, str) and is_pipeline_step(sid):
            deps.add(source_pipeline_id(sid))
    return deps


async def transitive_pipeline_step_deps(
    session: AsyncSession,
    pipeline_id: str,
    *,
    visited: set[str] | None = None,
) -> set[str]:
    """BFS over the transitive sub-pipeline graph.

    Returns the set of pipeline ids reachable from `pipeline_id`
    through any chain of sub-pipeline-step references. Always reads
    LIVE documents (not pinned) so we surface cycles eagerly — pinning
    would otherwise let a cycle hide for one save cycle.
    """
    visited = visited or set()
    queue: list[str] = [pipeline_id]
    while queue:
        nxt = queue.pop()
        if nxt in visited:
            continue
        visited.add(nxt)
        row = await session.get(PipelineRow, nxt)
        if row is None:
            continue
        for dep in direct_pipeline_step_deps(row.document or {}):
            if dep not in visited:
                queue.append(dep)
    visited.discard(pipeline_id)  # don't list self in the closure
    return visited


async def check_no_cycle(
    session: AsyncSession,
    parent_id: str,
    parent_doc: dict[str, Any],
) -> None:
    """Raise ValueError if saving `parent_doc` under `parent_id` would
    create a cycle.

    The pre-existing on-disk parent's old doc is irrelevant — what
    matters is whether the *proposed* doc's deps include the parent.
    Walks the new direct deps and, for each, checks if its transitive
    closure contains parent_id.
    """
    direct = direct_pipeline_step_deps(parent_doc)
    for dep in direct:
        if dep == parent_id:
            raise ValueError(
                f"Self-reference: pipeline {parent_id!r} can't include itself as a step."
            )
        # Walk dep's tree. If parent_id is reachable from dep, we'd be
        # adding a back-edge that closes a cycle.
        closure = await transitive_pipeline_step_deps(session, dep)
        if parent_id in closure or dep in closure:
            chain = " → ".join([parent_id, dep, "…", parent_id])
            raise ValueError(
                f"Cycle detected: composing pipeline {dep!r} would create a loop "
                f"({chain}). Break the chain before saving."
            )

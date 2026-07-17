"""Catalog API.

Workspace-wide cross-pipeline lineage. Walks every saved pipeline,
extracts its dataset references + output sinks, and builds a meta-graph
where each pipeline is a node and edges are inferred when one pipeline
reads what another produces.

For v1 (this milestone), edge detection is URI-based: an edge exists
from pipeline A → pipeline B when any of A's outputs writes to a path
that matches one of B's datasets (after path normalisation). External
consumers (Looker, Slack, etc.) come from optional `metadata.consumers`
on the pipeline document — not auto-detected yet (that's the
OpenLineage integration).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dig.storage.db import get_session
from dig.storage.models import Dataset
from dig.storage.models import Pipeline as PipelineRow
from dig.storage.models import Run

log = logging.getLogger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])


# ---- Schemas ------------------------------------------------------------


class CatalogNodeOut(BaseModel):
    """One node in the workspace-wide meta-graph."""
    id: str
    kind: str            # "pipeline" | "consumer"
    name: str
    description: str | None = None
    # Aggregated state — drives the overlays at meta-level.
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    node_count: int = 0
    group_count: int = 0
    # Dataset refs (pipeline reads from these) and output sinks
    # (pipeline writes to these). Surfaced for the side panel.
    inputs: list[str] = []
    outputs: list[str] = []
    # User-applied tags from the pipeline document.
    # Powers the catalog tag-filter chips + the workspace search.
    tags: list[str] = []


class CatalogEdgeOut(BaseModel):
    """A→B edge: pipeline A produces output, pipeline B reads it."""
    from_id: str
    to_id: str
    # The matching path / dataset uri, for debugging + tooltips.
    via: str | None = None
    # Column-level lineage. When a registered Dataset
    # row exists for `via`, we attach its column names so the catalog
    # frontend can render "→ N columns flow through this edge" and an
    # expandable list of column names. Empty when the URI is foreign
    # (e.g. a raw output sink without a corresponding registered dataset).
    columns: list[str] = []


class CatalogOut(BaseModel):
    nodes: list[CatalogNodeOut]
    edges: list[CatalogEdgeOut]


# ---- Helpers -----------------------------------------------------------


def _normalise_uri(uri: str | None) -> str:
    """file:///abs/path.parquet → /abs/path.parquet — so we match the
    same physical file regardless of how each pipeline references it."""
    if not uri:
        return ""
    if uri.startswith("file://"):
        return uri[len("file://"):]
    return uri


def _collect_inputs(doc: dict[str, Any]) -> list[str]:
    """Pipeline INPUTS = the dataset URIs it reads from."""
    out: list[str] = []
    for d in doc.get("datasets") or []:
        if isinstance(d, dict):
            uri = d.get("uri") or d.get("storageUri")
            if uri:
                out.append(_normalise_uri(uri))
    return out


def _collect_outputs(doc: dict[str, Any]) -> list[str]:
    """Pipeline OUTPUTS = the sink URIs it writes to. Only sinks count
    here; an OutputSpec without a sink is "preview-only" and doesn't
    appear in the catalog graph because nothing downstream can read it."""
    out: list[str] = []
    for o in doc.get("outputs") or []:
        if not isinstance(o, dict):
            continue
        sink = o.get("sink")
        if isinstance(sink, dict):
            uri = sink.get("uri")
            if uri:
                out.append(_normalise_uri(uri))
    return out


# ---- Endpoint ----------------------------------------------------------


@router.get("/lineage", response_model=CatalogOut)
async def get_catalog_lineage(
    session: AsyncSession = Depends(get_session),
) -> CatalogOut:
    """Returns the workspace's cross-pipeline lineage graph."""
    # Load every pipeline (we don't paginate — catalog views are
    # all-or-nothing). For a workspace with thousands of pipelines this
    # would need to chunk, but real installs sit in single digits to
    # low hundreds.
    res = await session.execute(select(PipelineRow))
    pipelines = list(res.scalars().all())

    # Pre-load every dataset's columns so we can label cross-pipeline
    # edges with the column list flowing through them. Indexed by both
    # `source_uri` and `storage_uri` (each can match the URI a sink
    # writes to OR a downstream pipeline reads from), normalised the
    # same way as `_normalise_uri()`.
    # Column-only select: skips the heavy `profile` JSON blob, which
    # this endpoint never reads.
    ds_res = await session.execute(
        select(Dataset.source_uri, Dataset.storage_uri, Dataset.columns)
    )
    columns_by_uri: dict[str, list[str]] = {}
    for source_uri, storage_uri, ds_columns in ds_res.all():
        cols = [
            c.get("name") for c in (ds_columns or [])
            if isinstance(c, dict) and isinstance(c.get("name"), str)
        ]
        cols = [c for c in cols if c]
        for u in (source_uri, storage_uri):
            key = _normalise_uri(u)
            if key and key not in columns_by_uri:
                columns_by_uri[key] = cols

    # Latest run per pipeline — used to surface last_run_status +
    # last_run_at on each node. Windowed subquery so SQLite returns one
    # row per pipeline instead of us scanning the whole runs table
    # (with its heavy JSON columns) in Python.
    ranked = (
        select(
            Run.pipeline_id,
            Run.status,
            Run.finished_at,
            func.row_number()
            .over(partition_by=Run.pipeline_id, order_by=Run.created_at.desc())
            .label("rn"),
        )
        .subquery()
    )
    runs_res = await session.execute(
        select(ranked.c.pipeline_id, ranked.c.status, ranked.c.finished_at)
        .where(ranked.c.rn == 1)
    )
    latest_run_by_pipeline = {row.pipeline_id: row for row in runs_res.all()}

    nodes: list[CatalogNodeOut] = []
    inputs_by_pipeline: dict[str, list[str]] = {}
    outputs_by_pipeline: dict[str, list[str]] = {}

    for p in pipelines:
        doc = p.document or {}
        inputs = _collect_inputs(doc)
        outputs = _collect_outputs(doc)
        inputs_by_pipeline[p.id] = inputs
        outputs_by_pipeline[p.id] = outputs

        latest = latest_run_by_pipeline.get(p.id)
        tags = [t for t in (doc.get("tags") or []) if isinstance(t, str)]
        nodes.append(CatalogNodeOut(
            id=p.id,
            kind="pipeline",
            name=doc.get("name") or p.id,
            description=doc.get("description"),
            last_run_at=latest.finished_at if latest else None,
            last_run_status=latest.status if latest else None,
            node_count=len(doc.get("nodes") or []),
            group_count=len(doc.get("groups") or []),
            inputs=inputs,
            outputs=outputs,
            tags=tags,
        ))

    # Edge detection: for every (A, B) pair, if any of A's outputs
    # matches any of B's inputs, emit A → B. O(P²) on number of
    # pipelines but cheap in practice.
    edges: list[CatalogEdgeOut] = []
    for a in pipelines:
        a_outs = outputs_by_pipeline.get(a.id, [])
        if not a_outs:
            continue
        for b in pipelines:
            if b.id == a.id:
                continue
            b_ins = inputs_by_pipeline.get(b.id, [])
            for out in a_outs:
                if out in b_ins:
                    edges.append(CatalogEdgeOut(
                        from_id=a.id,
                        to_id=b.id,
                        via=out,
                        columns=columns_by_uri.get(out, []),
                    ))
                    break  # one edge per pair is enough; tooltip can show all

    return CatalogOut(nodes=nodes, edges=edges)

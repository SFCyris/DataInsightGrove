from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.engine.compile import compile_for_browser
from dig.engine.compile_python import compile_to_notebook, compile_to_python, unsupported_steps
from dig.engine.dag import DagError, infer_schemas, validate, validate_params_against_manifests
from dig.engine.diff import diff_pipelines
from dig.engine.executor import compile_to_sql
from dig.engine.history import snapshot_pipeline
from dig.engine.lineage import trace_column
from dig.engine.pipeline import Pipeline
from dig.engine.registry import steps
from dig.jobs.hub import hub
from dig.jobs.manager import jobs
from dig.storage.db import get_session
from dig.storage.models import Pipeline as PipelineRow
from dig.storage.models import PipelineHistory
from dig.storage.models import Run

log = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class PipelineSummary(BaseModel):
    id: str
    name: str
    nodeCount: int
    datasetCount: int
    outputCount: int
    etag: int
    createdAt: datetime
    updatedAt: datetime
    # ── Data-health flags so the pipelines list can show a "⚠ Missing data"
    # badge when an input dataset has been deleted or a previous run's
    # output files have been removed from disk. Counts (not booleans) so
    # the UI can show "2 missing inputs" in a tooltip rather than a vague
    # warning. Both default to 0 — pipelines created or saved without
    # local-file references will always read as healthy.
    missingDatasetCount: int = 0
    missingOutputCount: int = 0


class PipelineDoc(BaseModel):
    """API envelope: id, etag, and the pipeline document."""

    id: str
    etag: int
    document: dict[str, Any]
    createdAt: datetime
    updatedAt: datetime


class CreatePipelineRequest(BaseModel):
    name: str
    document: dict[str, Any] | None = None


class UpdatePipelineRequest(BaseModel):
    document: dict[str, Any]
    expectedEtag: int | None = None
    # When omitted, defaults to "manual_save" for backward compatibility with
    # external integrations. The editor passes "autosave" so the snapshot
    # retention policy treats it as transient (last 5 only) instead of as a
    # first-class checkpoint.
    triggeredBy: str | None = Field(default=None, pattern="^(manual_save|autosave|import|restore)$")
    # Optional free-text label/note. Only persisted when triggeredBy is
    # "manual_save" — autosaves don't carry meaningful labels.
    changeReason: str | None = None


class ClonePipelineRequest(BaseModel):
    name: str
    # Optional — clone the document at a specific snapshot. Defaults to
    # cloning the current live document.
    fromSnapshotId: str | None = None


class RunRequest(BaseModel):
    sampleRows: int | None = Field(default=None, ge=1, le=1_000_000)


class RunOut(BaseModel):
    id: str
    pipelineId: str
    status: str
    progress: float
    error: str | None = None
    outputPaths: list[str] | None = None
    # { output_id: [ {kind: "image"|"file"|"db"|"sink", …}, … ] }
    artifacts: dict[str, list[dict[str, Any]]] | None = None
    startedAt: datetime | None = None
    finishedAt: datetime | None = None
    createdAt: datetime


def _empty_doc(name: str, pid: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "id": pid,
        "name": name,
        "datasets": [],
        "nodes": [],
        "outputs": [],
    }


# Connectors that resolve to local files we can stat. Other connectors
# (rest, jdbc, sftp, …) read from remote sources whose availability we
# can't cheaply check from the API process — those are skipped, treated as
# "available" for the purposes of the missing-data badge.
_LOCAL_FILE_CONNECTORS = frozenset({"parquet", "csv", "xlsx", "excel", "json", "jsonl"})


def _local_path(uri: str | None) -> str | None:
    """Return a stat-able local path for ``uri``, or None if it isn't local.

    URIs in pipeline documents come from dataset registration: parquet caches
    are stored as ``file:///abs/path.parquet`` (the Dataset row's storage_uri
    after the file:// prefix is added), and uploaded sources may also be
    file:// URIs. Anything with a non-file scheme (https, jdbc, …) is treated
    as remote.
    """
    if not uri:
        return None
    if uri.startswith("file://"):
        return uri[len("file://") :]
    if "://" not in uri:
        # Bare path — treat as local.
        return uri
    return None


def _count_missing_datasets(doc: dict[str, Any]) -> int:
    """Count dataset references in ``doc.datasets[]`` whose backing file is
    missing. Skips non-local connectors (we can't check those without a
    network round-trip)."""
    missing = 0
    for ds in doc.get("datasets", []) or []:
        if not isinstance(ds, dict):
            continue
        connector = str(ds.get("connector", "")).lower()
        if connector not in _LOCAL_FILE_CONNECTORS:
            continue
        path = _local_path(ds.get("uri"))
        if path is None:
            # Connector says local but URI isn't stat-able — treat as healthy
            # rather than scaring the user with a false positive.
            continue
        if not os.path.exists(path):
            missing += 1
    return missing


def _count_missing_outputs(latest_run: Run | None) -> int:
    """Count output files from the most recent successful run that no longer
    exist on disk. ``None`` (no runs yet) returns 0 — an unrun pipeline isn't
    "missing" output, it's just unrun."""
    if latest_run is None or not latest_run.output_paths:
        return 0
    missing = 0
    for raw in latest_run.output_paths:
        path = _local_path(raw)
        if path is None:
            continue
        if not os.path.exists(path):
            missing += 1
    return missing


def _summary(row: PipelineRow, latest_run: Run | None = None) -> PipelineSummary:
    doc = row.document or {}
    return PipelineSummary(
        id=row.id,
        name=row.name,
        nodeCount=len(doc.get("nodes", [])),
        datasetCount=len(doc.get("datasets", [])),
        outputCount=len(doc.get("outputs", [])),
        etag=row.etag,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
        missingDatasetCount=_count_missing_datasets(doc),
        missingOutputCount=_count_missing_outputs(latest_run),
    )


def _doc(row: PipelineRow) -> PipelineDoc:
    return PipelineDoc(
        id=row.id,
        etag=row.etag,
        document=row.document or {},
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


def _run_out(r: Run) -> RunOut:
    return RunOut(
        id=r.id,
        pipelineId=r.pipeline_id,
        status=r.status,
        progress=r.progress,
        error=r.error,
        outputPaths=r.output_paths,
        artifacts=r.artifacts,
        startedAt=r.started_at,
        finishedAt=r.finished_at,
        createdAt=r.created_at,
    )


@router.get("", response_model=list[PipelineSummary])
async def list_pipelines(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[PipelineSummary]:
    """Paginated newest-first list. Default page is 100; max 500.

    The previous form returned every row and computed counts by parsing
    each `document` blob — fine for a hobby corpus, OOM-y for any larger
    install. Pagination is mandatory; the home page asks for the first
    page, the dropdown switcher asks for `?limit=10&offset=0`, etc.
    """
    capped = max(1, min(limit, 500))
    res = await session.execute(
        select(PipelineRow)
        .order_by(PipelineRow.updated_at.desc())
        .limit(capped)
        .offset(max(0, offset))
    )
    rows = res.scalars().all()
    # Batch-fetch the latest succeeded run per pipeline so the missing-output
    # check on _summary() doesn't fan out into N queries. We pull all
    # succeeded runs for the page's pipelines in one shot, sorted newest-
    # first, and keep the first row per pipeline_id.
    latest_runs: dict[str, Run] = {}
    if rows:
        runs_res = await session.execute(
            select(Run)
            .where(Run.pipeline_id.in_([r.id for r in rows]))
            .where(Run.status == "succeeded")
            .order_by(Run.pipeline_id, Run.created_at.desc())
        )
        for run in runs_res.scalars().all():
            latest_runs.setdefault(run.pipeline_id, run)
    return [_summary(r, latest_runs.get(r.id)) for r in rows]


@router.post("", response_model=PipelineDoc, status_code=201)
async def create_pipeline(
    req: CreatePipelineRequest, session: AsyncSession = Depends(get_session)
) -> PipelineDoc:
    pid = str(ULID())
    doc = req.document or _empty_doc(req.name, pid)
    # If document has its own id, override with our ULID for consistency.
    doc["id"] = pid
    doc.setdefault("name", req.name)
    row = PipelineRow(id=pid, name=req.name, document=doc, etag=1)
    session.add(row)
    # Snapshot the initial state so subsequent edits have a "previous" to
    # diff against. Triggered_by mirrors import — both are "starting points."
    await snapshot_pipeline(
        session, pid, doc, 1, triggered_by="import"
    )
    await session.commit()
    return _doc(row)


@router.get("/{pipeline_id}", response_model=PipelineDoc)
async def get_pipeline(
    pipeline_id: str, session: AsyncSession = Depends(get_session)
) -> PipelineDoc:
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    return _doc(row)


@router.put("/{pipeline_id}", response_model=PipelineDoc)
async def update_pipeline(
    pipeline_id: str,
    req: UpdatePipelineRequest,
    session: AsyncSession = Depends(get_session),
) -> PipelineDoc:
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    # ETag enforcement: previously a client that omitted expectedEtag could
    # silently overwrite a concurrent edit from another tab. Require the
    # client to send it; the WS pipeline_changed event keeps clients in sync.
    if req.expectedEtag is None:
        raise HTTPException(
            400,
            "expectedEtag is required for updates. "
            "Pass the etag returned from GET /pipelines/{id}.",
        )
    if req.expectedEtag != row.etag:
        raise HTTPException(409, f"stale etag (have {req.expectedEtag}, current {row.etag})")
    doc = dict(req.document)
    doc["id"] = pipeline_id  # don't let the doc rewrite its own id
    name = doc.get("name")
    if name:
        row.name = str(name)
    # Cycle detection: a parent referencing a sub-pipeline whose closure
    # includes itself would create an infinite expansion at compile time.
    # Reject with a 409 so the editor can surface a helpful warning.
    from dig.engine.pipeline_step import check_no_cycle as _check_no_cycle
    try:
        await _check_no_cycle(session, pipeline_id, doc)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e

    row.document = doc
    row.etag = (row.etag or 0) + 1
    # History snapshot (deduped by document hash — UI-coord-only saves no-op).
    # `triggeredBy` defaults to "manual_save" for back-compat; the editor
    # passes "autosave" for incidental keystroke-driven saves so retention
    # can keep them on a short tail.
    trigger = req.triggeredBy or "manual_save"
    reason = req.changeReason if trigger == "manual_save" else None
    await snapshot_pipeline(
        session, pipeline_id, doc, row.etag,
        triggered_by=trigger, change_reason=reason,
    )
    await session.commit()
    # broadcast (Phase 5 will use this for multi-session sync)
    await hub.publish(f"pipeline:{pipeline_id}", {"event": "changed", "etag": row.etag})
    return _doc(row)


@router.post("/{pipeline_id}/clone", response_model=PipelineDoc, status_code=201)
async def clone_pipeline(
    pipeline_id: str,
    req: ClonePipelineRequest,
    session: AsyncSession = Depends(get_session),
) -> PipelineDoc:
    """Save As — clone an existing pipeline to a new id with a new name.

    Optionally clones from a specific history snapshot rather than the live
    document. The new pipeline gets a fresh etag=1 and an "import"-tagged
    initial snapshot so its history starts clean.
    """
    src = await session.get(PipelineRow, pipeline_id)
    if src is None:
        raise HTTPException(404, "pipeline not found")

    if req.fromSnapshotId:
        from dig.storage.models import PipelineHistory
        snap = await session.get(PipelineHistory, req.fromSnapshotId)
        if snap is None or snap.pipeline_id != pipeline_id:
            raise HTTPException(404, "snapshot not found for this pipeline")
        source_doc = dict(snap.document)
    else:
        source_doc = dict(src.document or {})

    # Mint a fresh id and rewrite the doc so it owns its new identity.
    from ulid import ULID
    new_id = str(ULID())
    new_doc = dict(source_doc)
    new_doc["id"] = new_id
    new_doc["name"] = req.name

    new_row = PipelineRow(id=new_id, name=req.name, document=new_doc, etag=1)
    session.add(new_row)
    await session.flush()
    await snapshot_pipeline(
        session, new_id, new_doc, 1,
        triggered_by="import",
        change_reason=f"Save As from {pipeline_id}",
    )
    await session.commit()
    return _doc(new_row)


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(
    pipeline_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    await session.delete(row)
    await session.commit()


# ---- Pipeline history & diff ---------------------------------------------


class HistoryEntry(BaseModel):
    id: str
    pipelineId: str
    etag: int
    changeSummary: str | None = None
    changeReason: str | None = None
    triggeredBy: str
    documentHash: str
    runId: str | None = None
    createdAt: datetime


class DiffRequest(BaseModel):
    """Either side may name a snapshot id, "current" (live document), or
    "run:<run_id>" (the snapshot taken when that run started)."""

    fromRef: str = Field(default="previous")
    toRef: str = Field(default="current")


# ---- Response models for v0.6 routes that previously returned `dict[str, Any]`
# (which made FastAPI emit `{}` in OpenAPI and broke the typed-paths story
# for clients other than DIG's own hand-typed `client.ts`). These mirror the
# actual route returns; values are shaped permissively (Any-typed nested
# dicts) where the underlying engine emits structures we don't want to
# duplicate-type here, but the route shapes themselves are now contractual.


class SnapshotOut(BaseModel):
    id: str
    pipelineId: str
    etag: int
    document: dict[str, Any]
    changeSummary: str | None = None
    changeReason: str | None = None
    triggeredBy: str
    documentHash: str
    runId: str | None = None
    createdAt: datetime


class ParamDiffOut(BaseModel):
    key: str
    a_value: Any = None
    b_value: Any = None
    a_summary: str
    b_summary: str


class StepDiffOut(BaseModel):
    kind: str
    node_id: str
    label: str
    step_type: str
    a_position: int | None = None
    b_position: int | None = None
    param_changes: list[ParamDiffOut] = Field(default_factory=list)


class DatasetDiffOut(BaseModel):
    kind: str
    dataset_id: str
    label: str
    option_changes: list[ParamDiffOut] = Field(default_factory=list)


class OutputDiffOut(BaseModel):
    kind: str
    output_id: str
    name: str
    a_from: str | None = None
    b_from: str | None = None


class PipelineDiffOut(BaseModel):
    summary: str
    counts: dict[str, int]
    steps: list[StepDiffOut]
    datasets: list[DatasetDiffOut]
    outputs: list[OutputDiffOut]
    metadata_changes: list[ParamDiffOut]


class ColumnLineageNodeOut(BaseModel):
    node_id: str
    is_dataset: bool
    column: str
    label: str
    transform: str
    expression: str | None = None


class ColumnLineageEdgeOut(BaseModel):
    from_node_id: str
    from_column: str
    to_node_id: str
    to_column: str
    transform: str


class ColumnLineageOut(BaseModel):
    target_node_id: str
    target_column: str
    nodes: list[ColumnLineageNodeOut]
    edges: list[ColumnLineageEdgeOut]


class NodeStatusOut(BaseModel):
    ok: bool
    error: str | None = None


class ValidateOut(BaseModel):
    ok: bool
    errors: list[str]
    schemas: dict[str, dict[str, str]]
    nodeStatus: dict[str, NodeStatusOut]


class PipelineExportOut(BaseModel):
    """Self-contained `.dig.json` envelope written by `/pipelines/{id}/export`."""
    model_config = ConfigDict(populate_by_name=True)
    dig_envelope: str = Field(alias="$dig")
    exportedAt: str
    etag: int
    name: str
    document: dict[str, Any]


class CompileOut(BaseModel):
    sql: str
    files: list[dict[str, Any]] = Field(default_factory=list)
    needs_spatial: bool = False


class PreviewOut(BaseModel):
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    rowCount: int | None = None
    sampleRows: int | None = None
    fellBackToBackend: bool = False


class RunsDiffOut(BaseModel):
    counts: dict[str, int]
    added: list[Any] = Field(default_factory=list)
    dropped: list[Any] = Field(default_factory=list)
    changed: list[Any] = Field(default_factory=list)
    joinKey: str | None = None


@router.get("/{pipeline_id}/history", response_model=list[HistoryEntry])
async def list_pipeline_history(
    pipeline_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[HistoryEntry]:
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    rows = (
        await session.execute(
            select(PipelineHistory)
            .where(PipelineHistory.pipeline_id == pipeline_id)
            .order_by(PipelineHistory.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
    ).scalars().all()
    return [
        HistoryEntry(
            id=r.id,
            pipelineId=r.pipeline_id,
            etag=r.etag,
            changeSummary=r.change_summary,
            changeReason=r.change_reason,
            triggeredBy=r.triggered_by,
            documentHash=r.document_hash,
            runId=r.run_id,
            createdAt=r.created_at,
        )
        for r in rows
    ]


@router.get("/{pipeline_id}/history/{snapshot_id}", response_model=SnapshotOut)
async def get_pipeline_snapshot(
    pipeline_id: str,
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    snap = await session.get(PipelineHistory, snapshot_id)
    if snap is None or snap.pipeline_id != pipeline_id:
        raise HTTPException(404, "snapshot not found")
    return {
        "id": snap.id,
        "pipelineId": snap.pipeline_id,
        "etag": snap.etag,
        "document": snap.document,
        "changeSummary": snap.change_summary,
        "triggeredBy": snap.triggered_by,
        "createdAt": snap.created_at.isoformat(),
    }


async def _resolve_pipeline_doc(
    session: AsyncSession, pipeline_id: str, ref: str
) -> dict[str, Any]:
    """Resolve a side of the diff to a pipeline document.

    Accepts: snapshot ULID, "current", "previous" (the snapshot before
    "current"), or "run:<run_id>" (the snapshot taken when that run started).
    """
    if ref == "current":
        row = await session.get(PipelineRow, pipeline_id)
        if row is None:
            raise HTTPException(404, "pipeline not found")
        return row.document or {}

    if ref == "previous":
        # Snapshots are taken at save time, so the *latest* snapshot equals
        # the current document. "Previous" means the one before that — fall
        # back to the latest if there's only one (e.g. fresh import).
        rows = (
            await session.execute(
                select(PipelineHistory)
                .where(PipelineHistory.pipeline_id == pipeline_id)
                .order_by(PipelineHistory.created_at.desc())
                .limit(2)
            )
        ).scalars().all()
        if len(rows) >= 2:
            return rows[1].document
        if rows:
            return rows[0].document
        return {}

    if ref.startswith("run:"):
        run_id = ref[4:]
        # Resolve by the indexed `run_id` column on PipelineHistory.
        # The previous shape searched `r.document.get("runId")`, but the
        # snapshot writer never injected `runId` into the document — every
        # `run:` ref silently fell back to the latest run-start snapshot.
        rows = (
            await session.execute(
                select(PipelineHistory).where(
                    PipelineHistory.pipeline_id == pipeline_id,
                    PipelineHistory.run_id == run_id,
                )
            )
        ).scalars().all()
        if rows:
            return rows[0].document
        raise HTTPException(404, f"no run-start snapshot found for run {run_id}")

    snap = await session.get(PipelineHistory, ref)
    if snap is None or snap.pipeline_id != pipeline_id:
        raise HTTPException(404, f"snapshot {ref} not found for this pipeline")
    return snap.document


@router.post("/{pipeline_id}/diff", response_model=PipelineDiffOut)
async def diff_pipeline(
    pipeline_id: str,
    req: DiffRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Diff two pipeline document references (snapshot id / "current" / "run:")."""
    a_doc = await _resolve_pipeline_doc(session, pipeline_id, req.fromRef)
    b_doc = await _resolve_pipeline_doc(session, pipeline_id, req.toRef)
    return diff_pipelines(a_doc, b_doc)


@router.post("/{pipeline_id}/restore/{snapshot_id}", response_model=PipelineDoc)
async def restore_pipeline(
    pipeline_id: str,
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
) -> PipelineDoc:
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    snap = await session.get(PipelineHistory, snapshot_id)
    if snap is None or snap.pipeline_id != pipeline_id:
        raise HTTPException(404, "snapshot not found")
    new_doc = dict(snap.document)
    new_doc["id"] = pipeline_id
    row.document = new_doc
    row.etag = (row.etag or 0) + 1
    await snapshot_pipeline(
        session, pipeline_id, new_doc, row.etag, triggered_by="restore",
        change_reason=f"Restored from snapshot {snapshot_id[-8:]}",
    )
    await session.commit()
    await hub.publish(
        f"pipeline:{pipeline_id}", {"event": "changed", "etag": row.etag}
    )
    return _doc(row)


@router.get("/{pipeline_id}/lineage/columns/{node_id}/{column}", response_model=ColumnLineageOut)
async def get_column_lineage(
    pipeline_id: str,
    node_id: str,
    column: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trace a column's ancestry back to its dataset roots.

    Returns a graph (nodes + edges) showing every step + column that fed into
    the target. Pure-structural — uses each step's `column_dependencies()`
    declaration; works without running the pipeline.
    """
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    try:
        p = Pipeline.model_validate(row.document)
    except Exception as e:
        raise HTTPException(400, f"pipeline document is invalid: {e}") from e
    return trace_column(p, node_id, column)


@router.post("/{pipeline_id}/validate", response_model=ValidateOut)
async def validate_pipeline(
    pipeline_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Validate the pipeline + report per-node compile status.

    Response shape:
      {
        ok: bool,
        errors: [str, ...],
        schemas: { node_id: { col: type, ... }, ... },
        nodeStatus: { node_id: { ok: bool, error?: str } }
      }

    `nodeStatus` lets the editor mark broken steps in red — typical case is
    "user added a step that referenced a column dropped/renamed by an
    earlier step." The frontend pill turns red and the tooltip shows the
    specific compile error.
    """
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    # Inline-expand sub-pipelines BEFORE pydantic validation so the
    # validator (and downstream schema inference) sees a flat DAG.
    # Without this, every node whose step is `pipeline:<id>` shows up
    # as "unknown step" in the editor's per-node status panel.
    from dig.engine.pipeline_step_inline import inline_sub_pipelines
    try:
        flat_doc = await inline_sub_pipelines(session, row.document or {})
    except ValueError as e:
        return {
            "ok": False,
            "errors": [str(e)],
            "schemas": {},
            "nodeStatus": {},
        }
    try:
        p = Pipeline.model_validate(flat_doc)
    except Exception as e:
        return {
            "ok": False,
            "errors": [f"{type(e).__name__}: {e}"],
            "schemas": {},
            "nodeStatus": {},
        }

    # DAG-level validation runs first — if the structure is broken (cycle,
    # missing reference) we can't say anything per-node and return early.
    try:
        validate(p)
    except DagError as e:
        return {"ok": False, "errors": [str(e)], "schemas": {}, "nodeStatus": {}}
    except Exception as e:
        return {
            "ok": False,
            "errors": [f"{type(e).__name__}: {e}"],
            "schemas": {},
            "nodeStatus": {},
        }

    param_errs = validate_params_against_manifests(p)
    if param_errs:
        return {"ok": False, "errors": param_errs, "schemas": {}, "nodeStatus": {}}

    # Per-node compile probe. We try to compile the SQL with each node as
    # the terminal and report whether it succeeded. Schema inference is a
    # superset of compile validity (a node whose schema can't be inferred
    # also can't compile), so we feed compile errors into the response.
    from dig.engine.executor import compile_to_sql as _compile

    node_status: dict[str, dict[str, Any]] = {}
    for node in p.nodes:
        try:
            _compile(p, terminal=node.id)
            node_status[node.id] = {"ok": True}
        except Exception as e:
            node_status[node.id] = {
                "ok": False,
                "error": f"{type(e).__name__}: {e}"[:500],
            }

    schemas = {k: v for k, v in infer_schemas(p).items()}
    overall_ok = all(s.get("ok") for s in node_status.values()) if node_status else True
    return {
        "ok": overall_ok,
        "errors": [] if overall_ok else [
            f"{nid}: {s['error']}" for nid, s in node_status.items() if not s.get("ok")
        ],
        "schemas": schemas,
        "nodeStatus": node_status,
    }


@router.get("/{pipeline_id}/export", response_model=PipelineExportOut, response_model_by_alias=True)
async def export_pipeline(
    pipeline_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Export a pipeline as a portable JSON envelope.

    The downloaded file is a self-contained `.dig.json`: the pipeline document
    plus a small metadata header (exported-at, etag, name). Dataset references
    are kept as-is; the importer assigns a fresh ULID and the user can re-point
    URIs from the editor.
    """
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    return {
        "$dig": "pipeline-export.v1",
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "etag": row.etag,
        "name": row.name,
        "document": row.document,
    }


@router.post("/import", response_model=PipelineDoc, status_code=201)
async def import_pipeline(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> PipelineDoc:
    """Import a pipeline from a `.dig.json` envelope.

    Accepts either:
      - `{"$dig": "pipeline-export.v1", "name": "...", "document": {...}}`
      - or a bare pipeline document `{"schemaVersion": 1, ...}`
    """
    # Size cap: a pipeline doc above 2 MB is almost certainly a runaway
    # import. Configurable via DIG_MAX_PIPELINE_KB. Use a fast structural
    # estimate — counting nodes/datasets — and only re-serialize when that
    # exceeds the cap, so we don't double-buffer the body on the happy path.
    max_kb = int(os.environ.get("DIG_MAX_PIPELINE_KB", "2048"))
    rough_count = len(body.get("nodes") or []) + len(body.get("datasets") or [])
    if rough_count > 2000 or len(str(body)) > max_kb * 1024:
        body_size = len(json.dumps(body).encode())
        if body_size > max_kb * 1024:
            raise HTTPException(
                413,
                f"pipeline document exceeds {max_kb} KB cap (got {body_size // 1024} KB)",
            )

    if "$dig" in body and "document" in body:
        name = body.get("name") or body.get("document", {}).get("name") or "Imported pipeline"
        doc = body["document"]
    elif body.get("schemaVersion") == 1 and "nodes" in body:
        name = body.get("name") or "Imported pipeline"
        doc = body
    else:
        raise HTTPException(400, "not a recognized pipeline export envelope")

    if not isinstance(doc, dict):
        raise HTTPException(400, "document must be an object")

    # Validate via the Pipeline Pydantic model before storing — catches
    # malformed structure (missing id/name, bad ref shape, etc.) at import
    # time instead of at first run.
    try:
        Pipeline.model_validate({**doc, "id": "PLACEHOLDER", "name": doc.get("name", name)})
    except Exception as e:
        raise HTTPException(400, f"document fails schema validation: {e}") from e

    pid = str(ULID())
    new_doc = dict(doc)
    new_doc["id"] = pid
    new_doc["name"] = name
    row = PipelineRow(id=pid, name=name, document=new_doc, etag=1)
    session.add(row)
    # Snapshot the imported document — first history entry so the user can
    # always diff their later edits against the original import.
    await snapshot_pipeline(
        session, pid, new_doc, 1, triggered_by="import"
    )
    await session.commit()
    return _doc(row)


@router.get("/templates/list")
async def list_templates() -> list[dict[str, Any]]:
    """List bundled starter templates from the repo's `samples/templates/` folder."""
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parents[3]
    templates_dir = repo / "samples" / "templates"
    if not templates_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(templates_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            out.append(
                {
                    "slug": data.get("slug") or p.stem,
                    "title": data.get("title") or p.stem,
                    "summary": data.get("summary") or "",
                    "tags": data.get("tags") or [],
                    "needsSampleDataset": data.get("needsSampleDataset", False),
                    "stepCount": len(data.get("document", {}).get("nodes", [])),
                }
            )
        except Exception:
            log.exception("template %s invalid", p.name)
    return out


@router.post("/templates/{slug}", response_model=PipelineDoc, status_code=201)
async def create_from_template(
    slug: str, session: AsyncSession = Depends(get_session)
) -> PipelineDoc:
    """Create a new pipeline from a bundled template.

    If the template requires the demo dataset, ensure it's imported first and
    substitute its cached storage URI into the document.
    """
    from pathlib import Path as _Path

    # Whitelist `slug` to a safe character set before path-joining — without
    # this, `slug=../../../../etc/hosts` would happily resolve and `read_text`
    # would leak file contents back as a "template not found" exception body.
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_-]{1,80}", slug):
        raise HTTPException(400, "invalid template slug")
    repo = _Path(__file__).resolve().parents[3]
    templates_dir = (repo / "samples" / "templates").resolve()
    src = (templates_dir / f"{slug}.json").resolve()
    try:
        src.relative_to(templates_dir)
    except ValueError:
        raise HTTPException(400, "template path escapes the templates directory")
    if not src.is_file():
        raise HTTPException(404, f"template '{slug}' not found")
    tmpl = json.loads(src.read_text())
    doc = tmpl.get("document") or {}

    # Materialize placeholders.
    pid = str(ULID())
    doc_str = json.dumps(doc).replace("{{PIPELINE_ID}}", pid)

    if tmpl.get("needsSampleDataset"):
        # Templates can specify which demo CSV they need via `sampleDataset`
        # (basename without .csv). Defaults to customers-demo for backward
        # compat with templates predating spatial/vector samples.
        sample_basename = tmpl.get("sampleDataset", "customers-demo")
        sample_label = sample_basename.replace("-", " · ")
        sample_csv = repo / "samples" / f"{sample_basename}.csv"

        from sqlalchemy import select as _select
        from dig.storage.models import Dataset as _Dataset

        # Match by name so a template asking for cities-demo doesn't pick up
        # an existing customers-demo and vice versa.
        res = await session.execute(
            _select(_Dataset).where(_Dataset.connector == "csv").order_by(_Dataset.created_at.asc())
        )
        existing_demo = next(
            (d for d in res.scalars().all() if sample_basename in (d.name or "").lower().replace(" · ", "-")),
            None,
        )
        if existing_demo is None:
            # Inline import to avoid recursive HTTP self-call.
            from dig.engine.profile import profile_dataframe
            from dig.engine.registry import connectors as _connectors
            from dig.storage.files import cached_parquet_path, upload_path

            import polars as pl

            if not sample_csv.exists():
                raise HTTPException(500, f"demo CSV {sample_basename}.csv missing on disk")
            connector = _connectors().get("csv")
            ds_id = str(ULID())
            up = upload_path(ds_id, sample_csv.name)
            up.write_bytes(sample_csv.read_bytes())
            d = _Dataset(
                id=ds_id,
                name=f"demo · {sample_label.replace('demo · ', '')}",
                connector="csv",
                source_uri=f"file://{up}",
                options={"delimiter": ",", "header": True},
                file_size=up.stat().st_size,
                status="ingesting",
            )
            session.add(d)
            await session.commit()
            try:
                lf = connector.read(d.source_uri, d.options)
                cached = cached_parquet_path(ds_id)
                df = lf.collect()
                df.write_parquet(cached, compression="zstd")
                d.storage_uri = f"file://{cached}"
                d.row_count = df.height
                profile = profile_dataframe(pl.scan_parquet(cached))
                d.columns = profile["columns"]
                d.profile = profile
                d.status = "ready"
            except Exception as e:
                log.exception("template demo ingest failed")
                d.status = "failed"
                d.error = str(e)
            await session.commit()
            existing_demo = d

        if not existing_demo.storage_uri:
            raise HTTPException(500, "demo dataset not ready")
        doc_str = doc_str.replace("{{DEMO_DATASET_URI}}", existing_demo.storage_uri)

    new_doc = json.loads(doc_str)
    new_doc["id"] = pid
    name = tmpl.get("title") or slug

    row = PipelineRow(id=pid, name=name, document=new_doc, etag=1)
    session.add(row)
    await session.commit()
    return _doc(row)


@router.post("/from-dataset/{dataset_id}", response_model=PipelineDoc, status_code=201)
async def create_overview_from_dataset(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> PipelineDoc:
    """Generate a 1–3-step "overview" pipeline from a dataset's column profile.

    The pipeline contains an ``export_to_image`` node per chart, each reading
    directly from the dataset (parallel, not chained). The frontend opens the
    new pipeline and the live image preview renders inline within a second.

    Chart-pick heuristics — same shape as the column-menu ``Visualize`` action,
    upgraded for "show me a few different angles":

      • Most-variable numeric column   → histogram (the column with the
        highest std/mean ratio so a tightly-clustered field doesn't pip a
        wide-range one with a similar absolute std).
      • Lowest-cardinality categorical → bar of top-N value counts (we want
        the column the user is most likely to want to "slice by").
      • Second-most-variable numeric   → histogram (a complementary view of
        spread; only emitted when at least two numeric columns exist).

    Returns a fresh PipelineDoc — caller routes the user straight to
    ``/pipelines/<id>`` and the editor's StepImagePreview takes it from there.
    """
    from dig.storage.models import Dataset as _Dataset

    d = await session.get(_Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    if not d.storage_uri:
        raise HTTPException(409, "dataset is still ingesting — try again in a moment")

    columns = d.columns or []
    if not columns:
        raise HTTPException(400, "dataset has no profiled columns yet")

    def _is_numeric(t: str) -> bool:
        s = (t or "").lower()
        return any(k in s for k in ("int", "float", "double", "decimal", "number"))

    def _is_textual(t: str) -> bool:
        s = (t or "").lower()
        return any(k in s for k in ("string", "varchar", "utf8", "text"))

    # Score numerics by std/mean (coefficient of variation) so a column whose
    # values cluster tightly doesn't beat a column with the same absolute std
    # but a much wider spread. Fallback to raw std for columns without a mean
    # (rare; happens with all-NULL or all-zero columns).
    def _variation(c: dict[str, Any]) -> float:
        std = c.get("std")
        mean = c.get("mean")
        if std is None:
            return -1.0
        if mean is None or mean == 0:
            return float(std)
        return float(std) / max(abs(float(mean)), 1e-9)

    numeric = [c for c in columns if _is_numeric(c.get("type", ""))]
    numeric.sort(key=_variation, reverse=True)
    categorical = [
        c for c in columns
        if _is_textual(c.get("type", ""))
        and 2 <= (c.get("distinctCount") or 0) <= 20
    ]
    categorical.sort(key=lambda c: c.get("distinctCount") or 0)

    nodes: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    # Canonical doc-internal alias for the dataset: `ds_<ulid-lowercase>`.
    # The pipeline-doctor rule `ruleNonCanonicalDatasetId` flags any other
    # form (`ds_main`, etc.) so several preview surfaces (focused-dataset
    # grid, rule-based hints, lineage trace) can match the alias against
    # the registered dataset row by id. Building the alias canonically
    # here avoids the doctor pop-up on every fresh "🌱 Try with sample
    # data" → auto-overview-pipeline run.
    ds_alias = f"ds_{d.id.lower()}"

    def _add_chart(node_id: str, kind: str, x_col: str, label_emoji: str, x_offset: int) -> None:
        nodes.append({
            "id": node_id,
            "step": "export_to_image",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"port": "out", "ref": ds_alias}},
            "outputs": ["out"],
            "params": {
                "kind": kind,
                "x": x_col,
                "title": f"{x_col} — {'distribution' if kind == 'histogram' else 'top values'}",
                "format": "png",
            },
            "ui": {"x": x_offset, "y": 100, "label": f"{label_emoji} {x_col}"},
        })
        outputs.append({
            "id": f"o_{node_id}",
            "name": f"{x_col}_chart",
            "from": {"port": "out", "ref": node_id},
        })

    if numeric:
        _add_chart("n_chart_hist", "histogram", numeric[0]["name"], "📊", 280)
    if categorical:
        _add_chart("n_chart_bar", "bar_counts", categorical[0]["name"], "🏷", 540)
    if len(numeric) >= 2:
        _add_chart("n_chart_hist2", "histogram", numeric[1]["name"], "📊", 800)

    if not nodes:
        # No numerics, no low-cardinality categoricals — fall back to a chart
        # of the first column (whatever it is). Better than refusing to make
        # an overview for what is, by definition, an unusually shaped dataset.
        first = columns[0]
        kind = "histogram" if _is_numeric(first.get("type", "")) else "bar_counts"
        _add_chart("n_chart_default", kind, first["name"], "📊", 280)

    pid = str(ULID())
    name = f"📊 {d.name} — overview"
    doc = {
        "schemaVersion": 1,
        "id": pid,
        "name": name,
        "datasets": [{
            "id": ds_alias,
            # The pipeline reads from the dataset's *cached parquet* path,
            # so the connector here is always "parquet" — regardless of the
            # original ingest connector (csv, xlsx, jdbc, …). Using
            # d.connector here was a bug: the CSV reader would try to read
            # the parquet bytes as CSV and the schema-inference path would
            # come back empty, leaving column dropdowns blank in the editor
            # and the live image preview unable to find any columns.
            "connector": "parquet",
            "uri": d.storage_uri,
            "label": d.name,
        }],
        "nodes": nodes,
        "outputs": outputs,
    }

    row = PipelineRow(id=pid, name=name, document=doc, etag=1)
    session.add(row)
    # Snapshot so the user has a baseline to diff their tweaks against —
    # same pattern as templates and imports.
    await snapshot_pipeline(
        session, pid, doc, 1, triggered_by="import",
    )
    await session.commit()
    return _doc(row)


@router.post("/{pipeline_id}/compile", response_model=CompileOut)
async def compile_pipeline(
    pipeline_id: str,
    target: str = "browser",
    sample_rows: int | None = 100_000,
    terminal: str | None = None,
    terminalViewMode: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compile the pipeline to SQL + virtual-file bindings for browser execution.

    target='browser' returns SQL that runs unchanged on DuckDB-WASM, plus a list
    of files the frontend must fetch and register before executing.

    `terminal` selects the focus node — pass a node id to compile only the
    pipeline up to that step (used by the live-grid focused-step preview).
    Defaults to the last node in topological order.

    `terminalViewMode` is meaningful only when the terminal node is a join.
    Passing 'unmatched_left' / 'unmatched_right' rewrites the focused join's
    kind to the matching anti-* variant for diagnostic preview ("why didn't
    these rows match?"). 'matched' (default) leaves the SQL unchanged.
    """
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    try:
        # Sub-pipeline inlining happens BEFORE validation, so the
        # validator + topological sort see a flattened DAG. The inliner
        # is a no-op for pipelines without `pipeline:<id>` steps, which
        # keeps the cost negligible for the common case.
        from dig.engine.pipeline_step_inline import inline_sub_pipelines
        flat_doc = await inline_sub_pipelines(session, row.document or {})
        p = Pipeline.model_validate(flat_doc)
        validate(p)
        param_errs = validate_params_against_manifests(p)
        if param_errs:
            raise HTTPException(400, "invalid params: " + "; ".join(param_errs))
    except DagError as e:
        raise HTTPException(400, str(e)) from e
    if target != "browser":
        raise HTTPException(400, f"unsupported target '{target}'")
    view_mode = terminalViewMode or None
    if view_mode is not None and view_mode not in {"matched", "unmatched_left", "unmatched_right"}:
        raise HTTPException(400, f"invalid terminalViewMode '{view_mode}'")
    try:
        result = compile_for_browser(p, terminal=terminal, terminal_view_mode=view_mode)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    sql = result.sql
    if sample_rows:
        sql = f"{sql} LIMIT {int(sample_rows)}"
    return {
        "sql": sql,
        "files": [{"name": f.name, "url": f.url, "format": f.format} for f in result.files],
        "terminal": result.terminal,
        "sampleRows": sample_rows,
    }


# Tokens that imply the DuckDB spatial extension. Used to decide whether
# to LOAD spatial before executing the preview SQL — keep in sync with the
# matching list on the frontend (`requiresSpatialExtension` in dispatcher.ts).
_SPATIAL_TOKENS = (
    "GEOMETRY",
    "ST_DISTANCE", "ST_DWITHIN", "ST_CONTAINS", "ST_INTERSECTS", "ST_BUFFER",
    "ST_POINT", "ST_X", "ST_Y", "ST_TRANSFORM", "ST_GEOMFROMTEXT", "ST_GEOMFROMWKB",
    "ST_AREA", "ST_LENGTH", "ST_CENTROID", "ST_UNION",
)


def _requires_spatial(sql: str) -> bool:
    upper = sql.upper()
    return any(tok in upper for tok in _SPATIAL_TOKENS)


def _ensure_spatial(con) -> None:
    """Best-effort INSTALL + LOAD of the spatial extension.

    On a fresh machine the first INSTALL needs internet — if that fails
    we let the subsequent SQL execution surface the real error so the
    user sees something concrete (rather than a silent fallback)."""
    try:
        con.execute("INSTALL spatial;")
    except Exception as e:  # noqa: BLE001
        log.warning("preview: INSTALL spatial failed (will try LOAD anyway): %s", e)
    con.execute("LOAD spatial;")


@router.post("/{pipeline_id}/preview", response_model=PreviewOut)
async def preview_pipeline(
    pipeline_id: str,
    sample_rows: int = 100_000,
    preview_limit: int = 500,
    terminal: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run the pipeline on the backend DuckDB and return a sample for the live grid.

    Used as a transparent fallback when DuckDB-WASM in the browser can't run
    the SQL — the canonical case is the spatial extension (geographic /
    GEOMETRY functions), which isn't bundled with the WASM build. Returns
    rows in the same shape the frontend's local-preview path produces.
    """
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    try:
        p = Pipeline.model_validate(row.document)
        validate(p)
        param_errs = validate_params_against_manifests(p)
        if param_errs:
            raise HTTPException(400, "invalid params: " + "; ".join(param_errs))
    except DagError as e:
        raise HTTPException(400, str(e)) from e

    try:
        sql = compile_to_sql(p, terminal=terminal)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    sample_clause = f"{sql} LIMIT {int(sample_rows)}" if sample_rows else sql
    preview_sql = f"SELECT * FROM ({sample_clause}) AS __preview LIMIT {int(preview_limit)}"
    count_sql = f"SELECT count(*) FROM ({sample_clause}) AS __preview"

    def _run() -> dict[str, Any]:
        import duckdb
        import time

        t0 = time.perf_counter()
        con = duckdb.connect(database=":memory:")
        try:
            if _requires_spatial(sql):
                _ensure_spatial(con)
            cur = con.execute(preview_sql)
            cols = [{"name": d[0], "type": str(d[1])} for d in cur.description]
            rows_raw = cur.fetchall()
            row_count = int(con.execute(count_sql).fetchone()[0])
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
        finally:
            con.close()

        # Coerce non-JSON-native values to strings — geometry blobs, decimals,
        # dates, etc. The frontend grid renders strings fine and the user can
        # see the actual values; numeric ops on these aren't expected from a
        # preview anyway.
        def _coerce(v: Any) -> Any:
            if v is None or isinstance(v, (str, int, float, bool)):
                return v
            return str(v)

        out_rows = [
            {c["name"]: _coerce(v) for c, v in zip(cols, r)} for r in rows_raw
        ]
        return {
            "columns": cols,
            "rows": out_rows,
            "rowCount": row_count,
            "sampleRows": sample_rows,
            "elapsedMs": elapsed_ms,
        }

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("preview pipeline %s failed", pipeline_id)
        raise HTTPException(500, f"preview failed: {e}") from e


@router.post("/{pipeline_id}/preview-step-rows")
async def preview_step_rows(
    pipeline_id: str,
    terminal: str,
    sample_rows: int = 20_000,
    preview_limit: int = 500,
    session: AsyncSession = Depends(get_session),
):
    """Run a Polars-engine step on sampled upstream data and return its
    output **as JSON rows** (same shape as ``/preview``).

    This is the transparent-fallback path for the editor: when a user
    focuses a Polars-only step (e.g. ``anomaly_zscore``,
    ``changepoint_detection``, ``rolling``), DuckDB-WASM can't run it,
    so the editor calls this endpoint instead and pipes the result
    into the same live grid. The user sees the post-step data in the
    grid; an "via backend" badge tells them where it ran.

    Cheaper than ``/preview`` because we run only the focused step,
    not the whole DAG.
    """
    from dig.engine.executor import (
        _terminal_polars_node, compile_to_sql, _materialize_sql_to_polars,
        materialize_polars_ancestors,
    )
    from dig.engine.sampling import (
        SamplingConfig, adapt_to_schema, wrap_with_sampling,
    )
    from dig.engine.step import PolarsContext
    from dig.storage.files import data_dir as _data_dir

    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    try:
        # Inline-expand sub-pipelines so a polars terminal that happens
        # to live inside a published step still resolves.
        from dig.engine.pipeline_step_inline import inline_sub_pipelines
        flat_doc = await inline_sub_pipelines(session, row.document or {})
        p = Pipeline.model_validate(flat_doc)
        validate(p)
    except DagError as e:
        raise HTTPException(400, str(e)) from e

    # Pipeline-level sampling config. When set, the user's chosen
    # method (head / tail / random / systematic) wraps the final SQL.
    # Falling back to head(sample_rows) keeps the legacy behavior for
    # docs that haven't picked a method yet — same shape as the
    # browser's `wrapWithSampling` so backend + browser previews now
    # agree on sampling semantics.
    sampling_cfg = SamplingConfig.from_metadata((flat_doc.get("metadata") or {}).get("sampling"))
    if sampling_cfg is None and sample_rows:
        sampling_cfg = SamplingConfig(method="head", size=int(sample_rows))

    # Adapt the sampling config to the focused terminal's output schema.
    # Pipeline-level sampling is configured for the final output; when
    # previewing an upstream intermediate (e.g. one of the join's input
    # datasets) the configured column may not exist there yet. The
    # adapter degrades to head(size) in that case so the preview
    # doesn't 500 with "Referenced column not found in FROM clause".
    if sampling_cfg is not None and sampling_cfg.method in (
        "stratified", "per_group", "weighted", "time_bucket"
    ):
        try:
            from dig.engine.dag import infer_schemas
            schemas = infer_schemas(p)
            terminal_schema = schemas.get(terminal)
            sampling_cfg = adapt_to_schema(sampling_cfg, terminal_schema)
        except Exception:
            # Schema inference failure shouldn't break the preview —
            # fall through with the user's original cfg and let the
            # SQL layer surface the actual error.
            pass

    poly_node = _terminal_polars_node(p, terminal)
    is_sql_terminal = poly_node is None
    # Both flavors are supported: polars terminal → execute_polars;
    # SQL terminal → compile_to_sql with materialized overrides for
    # any polars ancestors. The dispatcher falls here whenever WASM
    # compile fails because of a polars step ANYWHERE in the chain,
    # so we have to handle both terminal types transparently.
    if is_sql_terminal:
        if not any(n.id == terminal for n in p.nodes) and not any(d.id == terminal for d in p.datasets):
            raise HTTPException(404, f"node/dataset '{terminal}' not found")

    step = steps().get(poly_node.step) if poly_node is not None else None

    # Per-pipeline preview cache for any incidental side-effect
    # artifacts the upstream materializer + this step write.
    preview_dir = _data_dir() / "outputs" / "__preview" / pipeline_id

    def _run() -> dict[str, Any]:
        import duckdb
        import polars as pl  # noqa: F401
        import time

        t0 = time.perf_counter()
        con = duckdb.connect(database=":memory:")
        try:
            # Pre-materialize every Polars ancestor of the terminal so
            # downstream steps see the right input rows. This is the
            # SAME pattern the executor uses for full runs.
            materialized = materialize_polars_ancestors(
                con, p, terminal,
                out_dir=preview_dir, sample_rows=sample_rows,
            )
            if is_sql_terminal:
                # SQL terminal with polars ancestors → compile-then-execute.
                # The `materialized` dict turns each polars-ancestor's
                # parquet into a CTE alias the SQL compiler picks up.
                sql = compile_to_sql(p, terminal=terminal, overrides=materialized)
                # Apply the pipeline's sampling method (head / tail /
                # random / systematic) to the compiled SQL — same path
                # the browser uses via `wrapWithSampling`.
                sql = wrap_with_sampling(sql, sampling_cfg)
                if _requires_spatial(sql):
                    _ensure_spatial(con)
                preview_sql = f"SELECT * FROM ({sql}) AS __preview LIMIT {int(preview_limit)}"
                count_sql = f"SELECT count(*) FROM ({sql}) AS __preview"
                cur = con.execute(preview_sql)
                cols = [{"name": d[0], "type": str(d[1])} for d in cur.description]
                raw_rows = cur.fetchall()
                row_count = int(con.execute(count_sql).fetchone()[0])

                def _coerce(v: Any) -> Any:
                    if v is None or isinstance(v, (str, int, float, bool)):
                        return v
                    return str(v)
                rows_out = [
                    {c["name"]: _coerce(v) for c, v in zip(cols, r)} for r in raw_rows
                ]
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return {
                    "columns": cols,
                    "rows": rows_out,
                    "rowCount": row_count,
                    "sampleRows": sample_rows,
                    "elapsedMs": elapsed_ms,
                }

            # Polars terminal — original path.
            assert poly_node is not None and step is not None
            input_frames: dict[str, Any] = {}
            for port, ref in poly_node.inputs.items():
                up_sql = compile_to_sql(p, terminal=ref.ref, overrides=materialized)
                # Same sampling treatment as the SQL-terminal branch so
                # polars-step inputs are sampled the same way as their
                # SQL-only siblings.
                up_sql = wrap_with_sampling(up_sql, sampling_cfg)
                if _requires_spatial(up_sql):
                    _ensure_spatial(con)
                input_frames[port] = _materialize_sql_to_polars(con, up_sql)
        finally:
            con.close()
        # Polars-terminal continuation (the SQL branch above already
        # returned). We need to re-open the connection scope for
        # execute_polars; but since execute_polars uses Polars (not
        # DuckDB) directly, no con needed here.
        assert poly_node is not None and step is not None
        ctx = PolarsContext(
            run_id="__preview",
            out_dir=preview_dir,
            node_id=poly_node.id,
        )
        result = step.execute_polars(input_frames, poly_node.params, ctx)
        df = result.output

        # Truncate to preview_limit so the wire payload stays small.
        # Even if the step produces millions of rows, we only ship the
        # first preview_limit to the grid.
        head = df.head(preview_limit) if preview_limit and df.height > preview_limit else df
        cols = [{"name": n, "type": str(head.schema[n])} for n in head.columns]

        # Coerce non-JSON-native cell values to strings (datetimes,
        # decimals, durations, structs, etc.). Same convention as the
        # backend /preview path.
        rows_out: list[dict[str, Any]] = []
        for r in head.iter_rows(named=True):
            out: dict[str, Any] = {}
            for k, v in r.items():
                if v is None or isinstance(v, (str, int, float, bool)):
                    out[k] = v
                else:
                    out[k] = str(v)
            rows_out.append(out)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "columns": cols,
            "rows": rows_out,
            "rowCount": df.height,
            "sampleRows": sample_rows,
            "elapsedMs": elapsed_ms,
        }

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("preview-step-rows %s/%s failed", pipeline_id, terminal)
        raise HTTPException(400, f"{e}") from e


@router.post("/{pipeline_id}/preview-step")
async def preview_step(
    pipeline_id: str,
    terminal: str,
    sample_rows: int = 20_000,
    session: AsyncSession = Depends(get_session),
):
    """Render a single Polars-engine step on sampled upstream data and
    return its first artifact (PNG / SVG for ``export_to_image``).

    This is the path the editor uses for the live chart preview while the
    user is tweaking chart params. It bypasses the run record (no row in
    the runs table, no history snapshot) — the artifact is written to a
    per-pipeline preview cache under ``data/outputs/__preview/<pid>/`` and
    overwritten in place each call. Sampled to keep render time well under
    a second; the full-fidelity image is only produced by ▶ Run.

    Errors:
      400 — terminal isn't a Polars step (no artifact to produce), or the
            step raised during render. Error body is the actual exception
            so humanizeSqlError can translate it.
      404 — pipeline or terminal node missing.
    """
    from fastapi.responses import FileResponse as _FileResponse

    from dig.engine.executor import (
        _terminal_polars_node, compile_to_sql, _materialize_sql_to_polars,
        materialize_polars_ancestors,
    )
    from dig.engine.step import PolarsContext
    from dig.storage.files import data_dir as _data_dir

    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    try:
        # Inline-expand sub-pipelines for parity with the executor + the
        # rows-preview endpoint.
        from dig.engine.pipeline_step_inline import inline_sub_pipelines
        flat_doc = await inline_sub_pipelines(session, row.document or {})
        p = Pipeline.model_validate(flat_doc)
        validate(p)
    except DagError as e:
        raise HTTPException(400, str(e)) from e

    poly_node = _terminal_polars_node(p, terminal)
    if poly_node is None:
        # Either the node id doesn't exist or it's a SQL step (which has no
        # artifact to render — the live grid already covers SQL preview).
        raise HTTPException(
            400,
            f"step '{terminal}' is not a Polars-engine step (no artifact to preview)",
        )

    step = steps().get(poly_node.step)

    # Per-pipeline preview cache. We bucket by pipeline so concurrent edits
    # to two different pipelines don't stomp each other's preview file.
    preview_dir = _data_dir() / "outputs" / "__preview" / pipeline_id
    preview_dir.mkdir(parents=True, exist_ok=True)

    def _render() -> Path:
        import polars as pl  # noqa: F401  (pulled in by Step.execute_polars)
        import duckdb

        con = duckdb.connect(database=":memory:")
        try:
            # Pre-materialize every Polars ancestor of the focused step.
            # This makes chains like rolling → export_to_image render
            # correctly: the chart sees the post-rolling rows, not the
            # raw passthrough.
            materialized = materialize_polars_ancestors(
                con, p, terminal,
                out_dir=preview_dir, sample_rows=sample_rows,
            )
            input_frames: dict[str, Any] = {}
            for port, ref in poly_node.inputs.items():
                up_sql = compile_to_sql(p, terminal=ref.ref, overrides=materialized)
                if sample_rows:
                    up_sql = f"{up_sql} LIMIT {int(sample_rows)}"
                if _requires_spatial(up_sql):
                    _ensure_spatial(con)
                input_frames[port] = _materialize_sql_to_polars(con, up_sql)
        finally:
            con.close()

        ctx = PolarsContext(
            run_id="__preview",
            out_dir=preview_dir,
            node_id=poly_node.id,
        )
        result = step.execute_polars(input_frames, poly_node.params, ctx)
        # Find the first file/image artifact. ``export_to_image`` always
        # produces one with kind=="image"; other Polars steps may produce
        # files (kind=="file") that we can serve the same way.
        for art in result.artifacts:
            kind = art.get("kind")
            path = art.get("path")
            if kind in ("image", "file") and path:
                return Path(path)
        raise ValueError(
            f"step '{poly_node.step}' produced no file/image artifact to preview",
        )

    try:
        artifact_path = await asyncio.to_thread(_render)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("preview-step %s/%s failed", pipeline_id, terminal)
        raise HTTPException(400, f"{e}") from e

    if not artifact_path.is_file():
        raise HTTPException(500, "render reported success but artifact is missing")

    # no-cache so live param edits show their effect immediately. Browsers
    # caching here would lock the user into seeing a stale preview after they
    # change `kind` or `x` — surprising and hard to debug.
    media_type = "image/svg+xml" if artifact_path.suffix.lower() == ".svg" else "image/png"
    return _FileResponse(
        artifact_path,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{pipeline_id}/python")
async def export_pipeline_python(
    pipeline_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Render the pipeline as a standalone Polars Python script.

    Frontend uses this to power the 'show as Python' editor view and the
    'download .py' button. Best-effort: unsupported steps emit a TODO with the
    raw params so the user can finish the line.
    """
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    p = Pipeline.model_validate(row.document)
    return {
        "pipelineId": pipeline_id,
        "name": row.name,
        "code": compile_to_python(p),
        "language": "python",
        # Steps that have no Python codegen — frontend surfaces this as a
        # warning before download so users don't get a silently-broken .py.
        "unsupportedSteps": unsupported_steps(p),
    }


@router.get("/{pipeline_id}/notebook")
async def export_pipeline_notebook(
    pipeline_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Render the pipeline as a Jupyter notebook (.ipynb document).

    Returns the raw notebook JSON; the client saves it as
    `<pipeline_name>.ipynb` for the user.
    """
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    p = Pipeline.model_validate(row.document)
    return compile_to_notebook(p)


@router.post("/{pipeline_id}/runs", response_model=RunOut, status_code=202)
async def start_run(
    pipeline_id: str,
    req: RunRequest,
    session: AsyncSession = Depends(get_session),
) -> RunOut:
    row = await session.get(PipelineRow, pipeline_id)
    if row is None:
        raise HTTPException(404, "pipeline not found")
    # Defense-in-depth cycle check: rejects sub-pipeline cycles even
    # if a doc was somehow saved through a back door (raw DB write,
    # restored from history, future migration). The save-time check
    # already runs but this is the last gate before the worker takes
    # ownership of the run.
    from dig.engine.pipeline_step import check_no_cycle as _check_no_cycle
    from dig.engine.pipeline_step_inline import inline_sub_pipelines
    try:
        await _check_no_cycle(session, pipeline_id, row.document or {})
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    try:
        # Inline-expand sub-pipelines so the executor sees a flat DAG.
        flat_doc = await inline_sub_pipelines(session, row.document or {})
        p = Pipeline.model_validate(flat_doc)
        validate(p)
        param_errs = validate_params_against_manifests(p)
        if param_errs:
            raise HTTPException(400, "invalid params: " + "; ".join(param_errs))
    except DagError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    # Submit first so we have the run_id to stamp on the snapshot.
    # The window between submit() and snapshot+commit is microseconds and
    # entirely on the API side — the worker doesn't depend on the snapshot
    # row existing yet (only on the runs row, which submit() creates).
    # Submit the FLATTENED pipeline so the worker doesn't need to know
    # about sub-pipeline composition.
    run_id = await jobs.submit(p, sample_rows=req.sampleRows)
    # Snapshot at run-start so we always have a "this is what ran" record,
    # even if the editor mutates the pipeline mid-run. The `run_id` column
    # is what the diff endpoint resolves `run:<id>` refs against.
    await snapshot_pipeline(
        session, pipeline_id, row.document, row.etag,
        triggered_by="run_start", run_id=run_id,
    )
    await session.commit()
    # Use a fresh session so we see the row the JobManager just committed.
    from dig.storage.db import SessionLocal

    async with SessionLocal() as fresh:
        r = await fresh.get(Run, run_id)
    if r is None:
        raise HTTPException(500, "run row not created")
    return _run_out(r)


@router.get("/{pipeline_id}/runs", response_model=list[RunOut])
async def list_runs(
    pipeline_id: str, session: AsyncSession = Depends(get_session), limit: int = 25
) -> list[RunOut]:
    res = await session.execute(
        select(Run).where(Run.pipeline_id == pipeline_id).order_by(Run.created_at.desc()).limit(limit)
    )
    return [_run_out(r) for r in res.scalars().all()]


# ---- Run-detail endpoints (mounted at /runs, not /pipelines) ----

runs_router = APIRouter(prefix="/runs", tags=["runs"])


@runs_router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)) -> RunOut:
    r = await session.get(Run, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    return _run_out(r)


@runs_router.get("/{run_id}/artifact")
async def get_run_artifact(
    run_id: str,
    path: str,
):
    """Serve a single artifact file produced by a run.

    `path` must resolve to a file inside data/outputs/<run_id>/ — anything
    outside is rejected. Used by the frontend to display PNGs from
    export_to_image steps inline.
    """
    from fastapi.responses import FileResponse as _FileResponse

    from dig.storage.files import data_dir as _data_dir

    safe_root = (_data_dir() / "outputs" / run_id).resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(safe_root)
    except ValueError:
        raise HTTPException(403, "artifact path escapes the run directory")
    if not target.is_file():
        raise HTTPException(404, "artifact not found")
    return _FileResponse(target, headers={"Cache-Control": "no-cache"})


@runs_router.get("/{run_id}/diff", response_model=RunsDiffOut)
async def diff_runs(
    run_id: str,
    other: str,
    output_id: str | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compare two runs of the same pipeline cell-by-cell.

    Returns counts (added / dropped / changed) plus the first `limit` example
    rows for each bucket. Matches rows by primary key when present (`id` or
    `pk` columns) and by row content otherwise.
    """
    a = await session.get(Run, run_id)
    b = await session.get(Run, other)
    if a is None or b is None:
        raise HTTPException(404, "one of the runs is missing")
    if not a.output_paths or not b.output_paths:
        raise HTTPException(409, "one of the runs has no outputs")

    def _pick(r: Run) -> str:
        if output_id is not None:
            # Match basename without extension exactly — `startswith` would
            # collide between e.g. `out.parquet` and `out2.parquet`.
            for path in r.output_paths:
                stem = os.path.splitext(os.path.basename(path))[0]
                if stem == output_id:
                    return path
        return r.output_paths[0]

    # Push the parquet reads + the diff loop off the event loop. For 1M-row
    # outputs the iter_rows loop below was minutes of stalled handlers.
    path_a, path_b = _pick(a), _pick(b)
    df_a, df_b = await asyncio.to_thread(
        lambda: (pl.read_parquet(path_a), pl.read_parquet(path_b))
    )

    # Choose a join key — prefer `id` or `pk`, else hash whole row.
    key_col: str | None = None
    for cand in ("id", "pk", "primary_key", "row_id"):
        if cand in df_a.columns and cand in df_b.columns:
            key_col = cand
            break

    if key_col is not None:
        # Polars-native bucketing: outer-join then classify with a single
        # `with_columns` instead of a Python row-loop. For 1M-row outputs
        # this is ~50× faster than the previous iter_rows path.
        return await asyncio.to_thread(
            _diff_keyed, df_a, df_b, key_col, limit,
        )

    # No key — fall back to row-hash set diff. Hashing happens in Polars
    # rather than per-row Python.
    return await asyncio.to_thread(_diff_unkeyed, df_a, df_b, limit)


def _diff_keyed(df_a, df_b, key_col: str, limit: int) -> dict[str, Any]:
    """Polars-native cell-by-cell diff. Pure function, no async."""
    common_cols = [c for c in df_a.columns if c in df_b.columns and c != key_col]
    joined = df_a.with_columns(pl.lit(True).alias("_in_a")).join(
        df_b.with_columns(pl.lit(True).alias("_in_b")),
        on=key_col, how="full", suffix="__b",
    )

    # Coalesce the duplicated key column from a full-outer join so we always
    # have a non-null `key_col` for every row (Polars 1.x emits both sides).
    if f"{key_col}__b" in joined.columns:
        joined = joined.with_columns(
            pl.coalesce([pl.col(key_col), pl.col(f"{key_col}__b")]).alias(key_col)
        )

    in_a = pl.col("_in_a").fill_null(False)
    in_b = pl.col("_in_b").fill_null(False)

    # Slice each bucket via filter + head — no Python materialization until
    # we send back the response.
    dropped_df = joined.filter(in_a & ~in_b).head(limit)
    added_df   = joined.filter(in_b & ~in_a).head(limit)

    # Changed: rows present on both sides where any common column differs.
    changed_pred = pl.lit(False)
    for c in common_cols:
        # null != null in SQL but we want them equal — match plain Python ==.
        diff_expr = (
            (pl.col(c) != pl.col(f"{c}__b"))
            | (pl.col(c).is_null() & pl.col(f"{c}__b").is_not_null())
            | (pl.col(c).is_not_null() & pl.col(f"{c}__b").is_null())
        )
        changed_pred = changed_pred | diff_expr.fill_null(False)
    changed_filter = in_a & in_b & changed_pred
    changed_df = joined.filter(changed_filter).head(limit)

    # Total counts via cheap aggregates.
    counts = joined.select(
        pl.sum(in_a & ~in_b).alias("dropped"),
        pl.sum(in_b & ~in_a).alias("added"),
        pl.sum(changed_filter).alias("changed"),
    ).row(0)

    only_a = [{"key": _stringify(k)} for k in dropped_df.get_column(key_col).to_list()]
    only_b = [{"key": _stringify(k)} for k in added_df.get_column(key_col).to_list()]
    changed_out: list[dict[str, Any]] = []
    for row in changed_df.iter_rows(named=True):
        diffs: dict[str, Any] = {}
        for c in common_cols:
            av, bv = row.get(c), row.get(f"{c}__b")
            if av != bv:
                diffs[c] = {"a": _stringify(av), "b": _stringify(bv)}
        if diffs:
            changed_out.append({"key": _stringify(row.get(key_col)), "diffs": diffs})

    return {
        "joinKey": key_col,
        "rowsA": df_a.height,
        "rowsB": df_b.height,
        "addedCount": int(counts[1] or 0),
        "droppedCount": int(counts[0] or 0),
        "changedCount": int(counts[2] or 0),
        "added": only_b,
        "dropped": only_a,
        "changed": changed_out,
    }


def _diff_unkeyed(df_a, df_b, limit: int) -> dict[str, Any]:
    """Set-diff on the whole row when no primary key is available."""
    # Use Polars's unique to compute set differences without going through
    # Python tuples for every row.
    common = [c for c in df_a.columns if c in df_b.columns]
    a_only = df_a.select(common).join(df_b.select(common), on=common, how="anti")
    b_only = df_b.select(common).join(df_a.select(common), on=common, how="anti")
    a_count = a_only.height
    b_count = b_only.height
    return {
        "joinKey": None,
        "rowsA": df_a.height,
        "rowsB": df_b.height,
        "addedCount": b_count,
        "droppedCount": a_count,
        "changedCount": 0,
        "added":   [list(_stringify(v) for v in r) for r in b_only.head(limit).iter_rows()],
        "dropped": [list(_stringify(v) for v in r) for r in a_only.head(limit).iter_rows()],
        "changed": [],
    }


@runs_router.get("/{run_id}/lineage")
async def get_run_lineage(
    run_id: str,
    row_index: int,
    output_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trace a single output row back to its source dataset rows.

    Requires the pipeline to have been run with `metadata.trackLineage=true`.
    The output parquet must contain `__dig_lineage_<dataset_id>` columns; this
    endpoint reads those for the chosen output row, then for each referenced
    dataset returns the matching source rows by row index.
    """
    from dig.engine.executor import LINEAGE_COL_PREFIX

    r = await session.get(Run, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    if not r.output_paths:
        raise HTTPException(409, f"run not ready (status={r.status})")
    target = r.output_paths[0]
    if output_id is not None:
        # Match basename without extension exactly — `startswith` would
        # collide between e.g. `out.parquet` and `out2.parquet`.
        for path in r.output_paths:
            stem = os.path.splitext(os.path.basename(path))[0]
            if stem == output_id:
                target = path
                break

    out_df = pl.scan_parquet(target).slice(row_index, 1).collect()
    if out_df.height == 0:
        raise HTTPException(404, f"row_index {row_index} out of range")
    lineage_cols = [c for c in out_df.columns if c.startswith(LINEAGE_COL_PREFIX)]
    if not lineage_cols:
        raise HTTPException(
            409,
            "this output has no lineage columns — set metadata.trackLineage=true on "
            "the pipeline and re-run, and avoid steps that drop columns "
            "(group_aggregate, pivot, select_columns).",
        )

    # Find the originating pipeline so we can locate the source datasets.
    pipe = await session.get(PipelineRow, r.pipeline_id)
    if pipe is None:
        raise HTTPException(500, "originating pipeline missing")
    datasets = (pipe.document or {}).get("datasets", [])
    ds_by_id = {d["id"]: d for d in datasets}

    sources: list[dict[str, Any]] = []
    for col in lineage_cols:
        ds_id = col[len(LINEAGE_COL_PREFIX):]
        idx = out_df.row(0, named=True)[col]
        if idx is None:
            continue
        ds = ds_by_id.get(ds_id)
        if ds is None:
            sources.append({"dataset_id": ds_id, "row_index": idx, "row": None})
            continue
        # Path containment: a malicious pipeline doc could set the dataset uri
        # to file:///etc/passwd; require the resolved path to live under
        # data_dir(). Same pattern as /runs/{id}/artifact above.
        from dig.storage.files import data_dir as _data_dir_fn
        ds_path_raw = ds["uri"].removeprefix("file://")
        try:
            ds_path = Path(ds_path_raw).resolve()
            ds_path.relative_to(_data_dir_fn().resolve())
        except (ValueError, OSError):
            sources.append({
                "dataset_id": ds_id, "row_index": int(idx),
                "row": {"_error": "dataset path is outside data_dir; refusing to read"},
            })
            continue
        connector = ds.get("connector", "parquet")
        try:
            if connector == "parquet":
                src_lf = pl.scan_parquet(ds_path)
            elif connector == "csv":
                src_lf = pl.scan_csv(ds_path)
            else:
                src_lf = None
            if src_lf is None:
                row = None
            else:
                # row_number is 1-based in DuckDB; offset accordingly. Push the
                # blocking collect off the event loop so concurrent requests
                # don't stall. Bind `lf`/`i` as defaults — without that, the
                # next loop iteration reassigns `src_lf`/`idx` before the
                # awaited coroutine runs and the lambda closes over the wrong
                # values.
                src_row_df = await asyncio.to_thread(
                    lambda lf=src_lf, i=idx: lf.slice(int(i) - 1, 1).collect()
                )
                if src_row_df.height == 0:
                    row = None
                else:
                    row = {k: _stringify(v) for k, v in src_row_df.row(0, named=True).items()}
        except Exception as exc:  # noqa: BLE001
            row = {"_error": str(exc)}
        sources.append({
            "dataset_id": ds_id,
            "dataset_label": ds.get("label") or ds.get("uri"),
            "row_index": int(idx),
            "row": row,
        })

    return {
        "runId": run_id,
        "outputRowIndex": row_index,
        "sources": sources,
    }


def _stringify(v: Any) -> Any:
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


@runs_router.get("/{run_id}/output")
async def get_run_output(
    run_id: str,
    output_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    r = await session.get(Run, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    if not r.output_paths:
        raise HTTPException(409, f"run not ready (status={r.status})")
    # First output by default; output_id selects by parquet basename.
    # Match basename without extension exactly — `startswith` would collide
    # between e.g. `out.parquet` and `out2.parquet`.
    target = r.output_paths[0]
    if output_id is not None:
        for path in r.output_paths:
            stem = os.path.splitext(os.path.basename(path))[0]
            if stem == output_id:
                target = path
                break
    # Push parquet I/O off the event loop so other API calls don't stall.
    df = await asyncio.to_thread(
        lambda: pl.scan_parquet(target).slice(offset, limit).collect()
    )
    cols = [{"name": c, "type": str(df.schema[c])} for c in df.columns]
    rows = []
    for row in df.iter_rows(named=True):
        out = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            out[k] = v
        rows.append(out)
    total = pl.scan_parquet(target).select(pl.len()).collect().item()
    return {
        "runId": run_id,
        "outputPath": target,
        "columns": cols,
        "rows": rows,
        "offset": offset,
        "limit": limit,
        "totalRows": total,
    }


# ---- WebSocket hub for run progress ----

ws_router = APIRouter(tags=["ws"])


@ws_router.websocket("/ws/runs/{run_id}")
async def ws_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    topic = f"run:{run_id}"
    await hub.subscribe(topic, ws)
    try:
        while True:
            # We accept (and ignore) incoming pings to detect disconnection.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(topic, ws)


@ws_router.websocket("/ws/pipelines/{pipeline_id}")
async def ws_pipeline(ws: WebSocket, pipeline_id: str) -> None:
    await ws.accept()
    topic = f"pipeline:{pipeline_id}"
    await hub.subscribe(topic, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(topic, ws)


# ---- Step library endpoint ----

steps_router = APIRouter(prefix="/steps", tags=["steps"])


def _enrich_manifest(step: Any) -> dict[str, Any]:
    """Return the step's manifest with a `source` field appended.

    The registry tags pack-loaded Step objects with `source = 'pack:<id>'`
    (see dig.engine.registry._load_pack_steps). Built-ins have no
    `source` attribute, so they get `'builtin'` here. The frontend uses
    this to render a provenance badge — small chip in the picker that
    tells the user 'this step came from pack X', so installing a pack
    has visible affordances in the editor.
    """
    m = dict(step.manifest)
    m["source"] = getattr(step, "source", None) or "builtin"
    return m


@steps_router.get("")
async def list_steps(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """Return the union of disk-loaded steps + DB-backed pipeline-steps.

    Pipeline-steps are pipelines whose document has
    `metadata.publishedAsStep` set. They appear in the picker like any
    other step, with a `source: "pipeline:<id>"` tag so the UI renders
    a 🪆 composite badge.
    """
    out = [_enrich_manifest(s) for s in steps().all()]
    from dig.engine.pipeline_step import list_published_pipelines
    out.extend(await list_published_pipelines(session))
    return out


@steps_router.get("/{step_id:path}")
async def get_step(
    step_id: str, session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get one step manifest. Supports `pipeline:<id>` for sub-pipeline steps.

    Path-converter is `:path` so the colon in `pipeline:<id>` doesn't
    trigger an URL-decode mismatch.
    """
    from dig.engine.pipeline_step import (
        is_pipeline_step,
        source_pipeline_id,
        synthesize_manifest,
    )
    if is_pipeline_step(step_id):
        pid = source_pipeline_id(step_id)
        row = await session.get(PipelineRow, pid)
        if row is None:
            raise HTTPException(404, f"source pipeline {pid!r} not found")
        m = synthesize_manifest(pid, row.document or {}, row.etag or 1)
        if m is None:
            raise HTTPException(
                404,
                f"pipeline {pid!r} is not published as a step "
                "(set metadata.publishedAsStep on its document).",
            )
        m["source"] = f"pipeline:{pid}"
        return m
    try:
        return _enrich_manifest(steps().get(step_id))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

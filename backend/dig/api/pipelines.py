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


def _summary(row: PipelineRow) -> PipelineSummary:
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
async def list_pipelines(session: AsyncSession = Depends(get_session)) -> list[PipelineSummary]:
    res = await session.execute(select(PipelineRow).order_by(PipelineRow.updated_at.desc()))
    return [_summary(r) for r in res.scalars().all()]


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
    row.document = doc
    row.etag = (row.etag or 0) + 1
    # History snapshot (deduped by document hash — UI-coord-only saves no-op).
    await snapshot_pipeline(
        session, pipeline_id, doc, row.etag, triggered_by="manual_save"
    )
    await session.commit()
    # broadcast (Phase 5 will use this for multi-session sync)
    await hub.publish(f"pipeline:{pipeline_id}", {"event": "changed", "etag": row.etag})
    return _doc(row)


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


@router.get("/{pipeline_id}/history/{snapshot_id}")
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


@router.post("/{pipeline_id}/diff")
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


@router.get("/{pipeline_id}/lineage/columns/{node_id}/{column}")
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


@router.post("/{pipeline_id}/validate")
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
    try:
        p = Pipeline.model_validate(row.document)
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


@router.get("/{pipeline_id}/export")
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

    repo = _Path(__file__).resolve().parents[3]
    src = repo / "samples" / "templates" / f"{slug}.json"
    if not src.exists():
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


@router.post("/{pipeline_id}/compile")
async def compile_pipeline(
    pipeline_id: str,
    target: str = "browser",
    sample_rows: int | None = 100_000,
    terminal: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compile the pipeline to SQL + virtual-file bindings for browser execution.

    target='browser' returns SQL that runs unchanged on DuckDB-WASM, plus a list
    of files the frontend must fetch and register before executing.

    `terminal` selects the focus node — pass a node id to compile only the
    pipeline up to that step (used by the live-grid focused-step preview).
    Defaults to the last node in topological order.
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
    if target != "browser":
        raise HTTPException(400, f"unsupported target '{target}'")
    try:
        result = compile_for_browser(p, terminal=terminal)
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


@router.post("/{pipeline_id}/preview")
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
    try:
        p = Pipeline.model_validate(row.document)
        validate(p)
        param_errs = validate_params_against_manifests(p)
        if param_errs:
            raise HTTPException(400, "invalid params: " + "; ".join(param_errs))
    except DagError as e:
        raise HTTPException(400, str(e)) from e
    # Submit first so we have the run_id to stamp on the snapshot.
    # The window between submit() and snapshot+commit is microseconds and
    # entirely on the API side — the worker doesn't depend on the snapshot
    # row existing yet (only on the runs row, which submit() creates).
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


@runs_router.get("/{run_id}/diff")
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


@steps_router.get("")
async def list_steps() -> list[dict[str, Any]]:
    return [s.manifest for s in steps().all()]


@steps_router.get("/{step_id}")
async def get_step(step_id: str) -> dict[str, Any]:
    try:
        return steps().get(step_id).manifest
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

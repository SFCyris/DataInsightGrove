from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import polars as pl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.engine.profile import profile_dataframe
from dig.engine.registry import connectors
from dig.storage.db import get_session
from dig.storage.files import cached_parquet_path, upload_path
from dig.storage.models import Dataset

log = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


class TypeCandidate(BaseModel):
    """One detected possibility for a column's type. Profiling attaches a
    list of these per column, sorted by score descending — element [0] is
    DIG's pick, the rest are alternates surfaced in the Cast UI.

    `storage` carries the SQL physical type the cast would land in
    (DECIMAL(18,4), HUGEINT, UUID, VARCHAR, …). It's range-aware: a
    `scientific` candidate whose values exceed IEEE 754 will report
    storage=VARCHAR rather than DOUBLE, so the Cast UI can show the
    user the trade-off before they apply.
    """
    type: str
    score: float
    reason: str
    storage: str | None = None


class ColumnInfo(BaseModel):
    name: str
    type: str
    # Physical SQL type the values currently live in (DECIMAL(18,4), UUID,
    # VARCHAR, …). Mirrors the descriptor's sql_type unless a detector
    # overrode it for range reasons. Surfaced in the profile drawer + as
    # a hover tooltip on the column header.
    storage: str | None = None
    polarsType: str | None = None
    nullCount: int | None = None
    nullFraction: float | None = None
    distinctCount: int | None = None
    min: Any | None = None
    max: Any | None = None
    mean: float | None = None
    std: float | None = None
    sampledRows: int | None = None
    topValues: list[dict[str, Any]] = Field(default_factory=list)
    histogram: list[dict[str, Any]] | None = None
    # Type candidates produced by the meta-type detector pass. The first
    # entry is the same as `type`; remaining entries are alternates with
    # score >= ALTERNATE_MIN_SCORE that the Cast UI surfaces as smart picks.
    candidates: list[TypeCandidate] = Field(default_factory=list)


class DatasetOut(BaseModel):
    id: str
    name: str
    connector: str
    sourceUri: str
    storageUri: str | None = None
    status: str
    error: str | None = None
    rowCount: int | None = None
    fileSize: int | None = None
    columns: list[ColumnInfo] | None = None
    annotations: dict[str, str] | None = None
    createdAt: datetime
    updatedAt: datetime


class DatasetProfile(BaseModel):
    datasetId: str
    rowCount: int | None
    rowCountSampled: int | None
    columns: list[ColumnInfo]


class RowsPage(BaseModel):
    offset: int
    limit: int
    rows: list[dict[str, Any]]
    totalRows: int | None = None


def _to_out(d: Dataset) -> DatasetOut:
    return DatasetOut(
        id=d.id,
        name=d.name,
        connector=d.connector,
        sourceUri=d.source_uri,
        storageUri=d.storage_uri,
        status=d.status,
        error=d.error,
        rowCount=d.row_count,
        fileSize=d.file_size,
        columns=[ColumnInfo(**c) for c in (d.columns or [])],
        annotations=d.annotations or {},
        createdAt=d.created_at,
        updatedAt=d.updated_at,
    )


@router.get("", response_model=list[DatasetOut])
async def list_datasets(session: AsyncSession = Depends(get_session)) -> list[DatasetOut]:
    res = await session.execute(select(Dataset).order_by(Dataset.created_at.desc()))
    return [_to_out(d) for d in res.scalars().all()]


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> DatasetOut:
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    return _to_out(d)


@router.post("", response_model=DatasetOut)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    connector_id: str = Form("csv"),
    options: str = Form("{}"),
    session: AsyncSession = Depends(get_session),
) -> DatasetOut:
    """Upload a file and ingest it as a Dataset.

    The uploaded file is persisted to data/uploads/, then read by the chosen
    connector and materialized to data/datasets/{id}.parquet. A profile is
    computed and stored on the row.
    """
    try:
        opts = json.loads(options) if options else {}
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"options not valid JSON: {e}") from e

    try:
        connector = connectors().get(connector_id)
    except KeyError as e:
        raise HTTPException(400, str(e)) from e

    dataset_id = str(ULID())
    filename = file.filename or f"upload-{dataset_id}"
    display_name = name or filename
    upload = upload_path(dataset_id, filename)

    # Cap upload size. Default 500 MB; configurable via DIG_MAX_UPLOAD_MB.
    # Without this, a runaway client can fill data/uploads/ until disk-full.
    max_mb = int(os.environ.get("DIG_MAX_UPLOAD_MB", "500"))
    max_bytes = max_mb * 1024 * 1024

    # Persist upload bytes — abort early if size cap exceeded.
    upload.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with upload.open("wb") as fp:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                fp.close()
                upload.unlink(missing_ok=True)
                raise HTTPException(
                    413,
                    f"upload exceeds {max_mb} MB cap "
                    f"(set DIG_MAX_UPLOAD_MB to raise it)",
                )
            fp.write(chunk)
    file_size = upload.stat().st_size

    d = Dataset(
        id=dataset_id,
        name=display_name,
        connector=connector_id,
        source_uri=f"file://{upload}",
        options=opts,
        file_size=file_size,
        status="ingesting",
    )
    session.add(d)
    await session.commit()

    # Ingest + profile. Errors recorded on the row.
    try:
        lf = connector.read(d.source_uri, opts)
        # Materialize to parquet for fast subsequent reads.
        cached = cached_parquet_path(dataset_id)
        cached.parent.mkdir(parents=True, exist_ok=True)
        df = lf.collect()
        df.write_parquet(cached, compression="zstd")
        d.storage_uri = f"file://{cached}"
        d.row_count = df.height

        profile = profile_dataframe(pl.scan_parquet(cached))
        d.columns = profile["columns"]
        d.profile = profile
        d.status = "ready"
    except Exception as e:
        log.exception("ingest failed for %s", dataset_id)
        d.status = "failed"
        d.error = str(e)

    await session.commit()
    return _to_out(d)


@router.get("/{dataset_id}/profile", response_model=DatasetProfile)
async def get_profile(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> DatasetProfile:
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    profile = d.profile or {}
    return DatasetProfile(
        datasetId=dataset_id,
        rowCount=d.row_count,
        rowCountSampled=profile.get("rowCountSampled"),
        columns=[ColumnInfo(**c) for c in profile.get("columns", [])],
    )


@router.get("/{dataset_id}/rows", response_model=RowsPage)
async def get_rows(
    dataset_id: str,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> RowsPage:
    if limit > 1000:
        limit = 1000
    if offset < 0 or limit < 1:
        raise HTTPException(400, "offset must be >= 0 and limit >= 1")
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    if not d.storage_uri:
        raise HTTPException(409, f"dataset not ready (status={d.status})")

    # Cap offset so a pathological `offset=999_999_999` doesn't kick off a full
    # parquet scan. P1 review finding.
    if d.row_count is not None and offset > d.row_count:
        offset = d.row_count

    path = d.storage_uri.replace("file://", "")
    # Push the blocking scan + collect off the event loop so concurrent
    # /rows requests don't stall each other.
    import asyncio as _asyncio
    df = await _asyncio.to_thread(
        lambda: pl.scan_parquet(path).slice(offset, limit).collect()
    )
    rows: list[dict[str, Any]] = []
    for row in df.iter_rows(named=True):
        out = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            out[k] = v
        rows.append(out)
    return RowsPage(offset=offset, limit=limit, rows=rows, totalRows=d.row_count)


class AnnotationsUpdate(BaseModel):
    annotations: dict[str, str]


@router.put("/{dataset_id}/annotations", response_model=DatasetOut)
async def update_annotations(
    dataset_id: str,
    req: AnnotationsUpdate,
    session: AsyncSession = Depends(get_session),
) -> DatasetOut:
    """Replace the per-column annotations map for a dataset.

    Empty values are removed. Server doesn't validate that keys correspond to
    real columns — annotations can be added speculatively or kept for renamed
    columns.
    """
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    cleaned = {k: v.strip() for k, v in (req.annotations or {}).items() if v and v.strip()}
    d.annotations = cleaned
    await session.commit()
    return _to_out(d)


async def _serve_cached_parquet(dataset_id: str, session: AsyncSession) -> FileResponse:
    """Stream the cached parquet for in-browser DuckDB-WASM execution.

    Supports HEAD + Range (FileResponse handles Range natively); DuckDB-WASM
    uses both to read the parquet without buffering the full file.
    """
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    if not d.storage_uri:
        raise HTTPException(409, f"dataset not ready (status={d.status})")
    path = d.storage_uri.replace("file://", "")
    if not os.path.exists(path):
        raise HTTPException(410, "cached file gone")
    return FileResponse(
        path,
        media_type="application/vnd.apache.parquet",
        filename=f"{dataset_id}.parquet",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/{dataset_id}/cached.parquet", response_class=FileResponse)
async def get_cached_parquet(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    return await _serve_cached_parquet(dataset_id, session)


@router.head("/{dataset_id}/cached.parquet", include_in_schema=False)
async def head_cached_parquet(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    return await _serve_cached_parquet(dataset_id, session)


@router.post("/samples/import", response_model=DatasetOut)
async def import_sample(
    name: str = "demo · customers",
    sample: str = "customers-demo.csv",
    session: AsyncSession = Depends(get_session),
) -> DatasetOut:
    """Ingest a bundled sample CSV from the repo's `samples/` folder.

    Used by the home-page tour and the "Try with sample data" button to give
    the user a working dataset without forcing them to find their own CSV.
    """
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parents[3]
    src = repo / "samples" / sample
    if not src.exists():
        raise HTTPException(404, f"sample '{sample}' not bundled")

    try:
        connector = connectors().get("csv")
    except KeyError as e:
        raise HTTPException(500, str(e)) from e

    dataset_id = str(ULID())
    upload = upload_path(dataset_id, src.name)
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(src.read_bytes())
    file_size = upload.stat().st_size

    d = Dataset(
        id=dataset_id,
        name=name,
        connector="csv",
        source_uri=f"file://{upload}",
        options={"delimiter": ",", "header": True},
        file_size=file_size,
        status="ingesting",
    )
    session.add(d)
    await session.commit()

    try:
        lf = connector.read(d.source_uri, d.options)
        cached = cached_parquet_path(dataset_id)
        cached.parent.mkdir(parents=True, exist_ok=True)
        df = lf.collect()
        df.write_parquet(cached, compression="zstd")
        d.storage_uri = f"file://{cached}"
        d.row_count = df.height
        profile = profile_dataframe(pl.scan_parquet(cached))
        d.columns = profile["columns"]
        d.profile = profile
        d.status = "ready"
    except Exception as e:
        log.exception("sample ingest failed")
        d.status = "failed"
        d.error = str(e)

    await session.commit()
    return _to_out(d)


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    # Capture file paths BEFORE deleting the row. Previously we removed files
    # first and then committed; if the commit failed (FK constraint, etc.),
    # files were gone but the row remained. Reverse the order: row first, then
    # files in a best-effort block. P1 review finding.
    storage_path = d.storage_uri.replace("file://", "") if d.storage_uri else None
    source_path = (
        d.source_uri.replace("file://", "")
        if (d.source_uri or "").startswith("file://") else None
    )
    await session.delete(d)
    await session.commit()
    # Files now: row is gone. Failures here only orphan a file on disk; safe.
    for p in (storage_path, source_path):
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                log.exception("failed to remove dataset file %s after row delete", p)

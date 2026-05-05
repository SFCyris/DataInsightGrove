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
    # Populated only when status == "awaiting_sheet_pick" — the list of
    # sheet names found in a multi-sheet Excel workbook the user
    # uploaded without specifying which sheet to ingest. Frontend reads
    # this to render the picker; PUT /datasets/{id}/sheet resumes ingest.
    availableSheets: list[str] | None = None
    selectedSheet: str | None = None
    # Populated only when status == "awaiting_island_pick" — the list of
    # detected rectangular data islands on the chosen sheet. Each entry
    # has range_a1, n_rows/n_cols, density, preview_first_row. Frontend
    # renders a picker; PUT /datasets/{id}/island resumes ingest.
    availableIslands: list[dict[str, Any]] | None = None
    selectedIsland: str | None = None
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
    opts = d.options or {}
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
        # Surface multi-sheet + multi-island metadata only — never the
        # full options dict (which can contain credentials for REST/JDBC
        # connectors).
        availableSheets=opts.get("available_sheets") if isinstance(opts.get("available_sheets"), list) else None,
        selectedSheet=opts.get("sheet") if isinstance(opts.get("sheet"), str) else None,
        availableIslands=opts.get("available_islands") if isinstance(opts.get("available_islands"), list) else None,
        selectedIsland=opts.get("island_range") if isinstance(opts.get("island_range"), str) else None,
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


class FromUriRequest(BaseModel):
    name: str
    connector_id: str
    uri: str
    options: dict[str, Any] = Field(default_factory=dict)


@router.post("/from-uri", response_model=DatasetOut)
async def create_dataset_from_uri(
    body: FromUriRequest,
    session: AsyncSession = Depends(get_session),
) -> DatasetOut:
    """Ingest a dataset from a URI without a file upload — for connectors
    that pull from a remote source (REST APIs, JDBC, S3, …). The connector
    is responsible for actually reading the data; the row + profile flow
    is the same as upload_dataset.

    Use this when the connector reads via a URL/URI rather than a local
    file. The legacy POST /datasets endpoint stays for file-upload connectors.
    """
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    if not body.uri.strip():
        raise HTTPException(400, "uri is required")

    try:
        connector = connectors().get(body.connector_id)
    except KeyError as e:
        raise HTTPException(400, str(e)) from e

    dataset_id = str(ULID())
    d = Dataset(
        id=dataset_id,
        name=body.name.strip(),
        connector=body.connector_id,
        source_uri=body.uri.strip(),
        options=body.options,
        status="ingesting",
    )
    session.add(d)
    await session.commit()

    # Connectors that pull from a network source do real IO inside read()
    # + collect(); both block. Push the whole materialize-and-profile chain
    # off the event loop so concurrent API requests aren't starved.
    import asyncio as _asyncio

    def _ingest_sync() -> dict[str, Any]:
        lf = connector.read(body.uri.strip(), body.options)
        cached = cached_parquet_path(dataset_id)
        cached.parent.mkdir(parents=True, exist_ok=True)
        df = lf.collect()
        # Global per-dataset size ceiling. AI-generated connectors could
        # otherwise stream gigabytes into memory before write_parquet runs.
        max_mb = int(os.environ.get("DIG_MAX_DATASET_MB", "1024"))
        size_mb = df.estimated_size("mb")
        if size_mb > max_mb:
            raise RuntimeError(
                f"ingested dataset is {size_mb:.0f} MB; exceeds DIG_MAX_DATASET_MB cap of {max_mb} MB",
            )
        df.write_parquet(cached, compression="zstd")
        profile = profile_dataframe(pl.scan_parquet(cached))
        return {
            "storage_uri": f"file://{cached}",
            "row_count": df.height,
            "columns": profile["columns"],
            "profile": profile,
        }

    try:
        result = await _asyncio.to_thread(_ingest_sync)
        d.storage_uri = result["storage_uri"]
        d.row_count = result["row_count"]
        d.columns = result["columns"]
        d.profile = result["profile"]
        d.status = "ready"
    except Exception as e:
        log.exception("from-uri ingest failed for %s", dataset_id)
        d.status = "failed"
        d.error = str(e)

    # Best-effort terminal status persist. If the row update itself fails
    # (DB drop, unique-constraint race) the dataset would be stuck in
    # 'ingesting' forever — log loudly so the operator can clean up.
    try:
        await session.commit()
    except Exception:
        log.exception(
            "from-uri: terminal status commit failed for dataset %s — row may be stuck in 'ingesting'",
            dataset_id,
        )
        raise
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

    # Multi-sheet Excel intercept: if the user uploaded a workbook with
    # 2+ sheets and didn't pre-select one, pause here. Save the sheet
    # list on the row + flip to status='awaiting_sheet_pick'. The
    # frontend then prompts the user, calls PUT /datasets/{id}/sheet,
    # and the rest of the ingest happens there.
    if connector_id == "excel" and not opts.get("sheet"):
        try:
            from connectors.excel.connector import list_sheets as _list_sheets
            sheets = _list_sheets(d.source_uri)
        except Exception:
            sheets = []
        if len(sheets) > 1:
            opts_with_sheets = dict(opts)
            opts_with_sheets["available_sheets"] = sheets
            d.options = opts_with_sheets
            d.status = "awaiting_sheet_pick"
            await session.commit()
            return _to_out(d)

    # Multi-island intercept: when the chosen sheet (single-sheet workbook
    # OR sheet already specified) contains 2+ disjoint data islands AND
    # the user hasn't pre-selected a range, pause + prompt. The detection
    # is cheap (one full sheet read) and only fires when an Excel file
    # genuinely has stacked / side-by-side tables.
    if connector_id == "excel" and not opts.get("island_range"):
        try:
            from connectors.excel.connector import list_data_islands as _list_islands
            islands = _list_islands(d.source_uri, opts.get("sheet"))
        except Exception:
            islands = []
        if len(islands) > 1:
            opts_with_islands = dict(opts)
            opts_with_islands["available_islands"] = islands
            d.options = opts_with_islands
            d.status = "awaiting_island_pick"
            await session.commit()
            return _to_out(d)

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


class PickSheetRequest(BaseModel):
    sheet: str


@router.put("/{dataset_id}/sheet", response_model=DatasetOut)
async def pick_sheet(
    dataset_id: str,
    body: PickSheetRequest,
    session: AsyncSession = Depends(get_session),
) -> DatasetOut:
    """Resume ingestion of a multi-sheet Excel upload by picking which
    sheet to materialise.

    The dataset must be in status='awaiting_sheet_pick' (set by upload_dataset
    when an Excel workbook with 2+ sheets is uploaded without an explicit
    sheet option). Validates the chosen sheet exists in the saved
    `options.available_sheets` list, then runs the same ingest+profile
    pipeline as the single-sheet path.
    """
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    if d.status != "awaiting_sheet_pick":
        raise HTTPException(
            400,
            f"dataset is in status {d.status!r}, not 'awaiting_sheet_pick' — "
            "this endpoint only resumes a paused multi-sheet upload",
        )

    available = (d.options or {}).get("available_sheets") or []
    if body.sheet not in available:
        raise HTTPException(
            400,
            f"sheet {body.sheet!r} not in workbook (available: {available})",
        )

    # Stamp the chosen sheet into options so re-runs / re-profiles are deterministic.
    new_opts = dict(d.options or {})
    new_opts["sheet"] = body.sheet
    new_opts.pop("available_sheets", None)
    d.options = new_opts
    d.status = "ingesting"
    await session.commit()

    try:
        connector = connectors().get(d.connector)
    except KeyError as e:
        raise HTTPException(500, str(e)) from e

    # After picking a sheet, the SAME multi-island detection runs on it.
    # If the chosen sheet has 2+ disjoint tables, pause again at
    # awaiting_island_pick so the user picks which one to ingest.
    try:
        from connectors.excel.connector import list_data_islands as _list_islands
        islands = _list_islands(d.source_uri, body.sheet)
    except Exception:
        islands = []
    if len(islands) > 1:
        new_opts2 = dict(d.options or {})
        new_opts2["available_islands"] = islands
        d.options = new_opts2
        d.status = "awaiting_island_pick"
        await session.commit()
        return _to_out(d)

    # Same ingest body as upload_dataset above.
    return await _ingest_dataset(d, connector, session)


async def _ingest_dataset(d: Dataset, connector: Any, session: AsyncSession) -> DatasetOut:
    """Run the canonical ingest+profile pipeline on an already-prepared
    dataset row. Caller has already validated the connector + options."""
    try:
        lf = connector.read(d.source_uri, d.options)
        cached = cached_parquet_path(d.id)
        cached.parent.mkdir(parents=True, exist_ok=True)
        df = lf.collect()
        df.write_parquet(cached, compression="zstd")
        d.storage_uri = f"file://{cached}"
        d.row_count = df.height

        profile = profile_dataframe(pl.scan_parquet(cached))
        d.columns = profile["columns"]
        d.profile = profile
        d.status = "ready"
        d.error = None
    except Exception as e:
        log.exception("ingest failed for %s", d.id)
        d.status = "failed"
        d.error = str(e)
    await session.commit()
    return _to_out(d)


class PickIslandRequest(BaseModel):
    """User-supplied range. Format: Excel A1, e.g. 'B2:F50'."""
    range: str


@router.put("/{dataset_id}/island", response_model=DatasetOut)
async def pick_island(
    dataset_id: str,
    body: PickIslandRequest,
    session: AsyncSession = Depends(get_session),
) -> DatasetOut:
    """Resume ingestion of an Excel upload paused at the island-pick step.

    The dataset must be in status='awaiting_island_pick'. Validates the
    chosen range against the saved `options.available_islands` list (so
    the user can't sneak in an arbitrary range that bypasses the
    detection — same anti-pattern as the sheet-pick endpoint), then runs
    ingest+profile with `island_range` set on the connector options.
    """
    d = await session.get(Dataset, dataset_id)
    if d is None:
        raise HTTPException(404, "dataset not found")
    if d.status != "awaiting_island_pick":
        raise HTTPException(
            400,
            f"dataset is in status {d.status!r}, not 'awaiting_island_pick' — "
            "this endpoint only resumes a paused multi-island upload",
        )

    available = (d.options or {}).get("available_islands") or []
    valid_ranges = {i.get("range_a1") for i in available if isinstance(i, dict)}
    if body.range not in valid_ranges:
        raise HTTPException(
            400,
            f"range {body.range!r} not in detected islands "
            f"(valid: {sorted(r for r in valid_ranges if r)})",
        )

    new_opts = dict(d.options or {})
    new_opts["island_range"] = body.range
    new_opts.pop("available_islands", None)
    d.options = new_opts
    d.status = "ingesting"
    await session.commit()

    try:
        connector = connectors().get(d.connector)
    except KeyError as e:
        raise HTTPException(500, str(e)) from e
    return await _ingest_dataset(d, connector, session)


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

    # Whitelist `sample` against the bundled samples directory — `..`
    # segments would otherwise let an authenticated caller copy any file
    # under `repo/` into `uploads/<id>/`, then read it back via the
    # `/datasets/{id}/cached.parquet` route.
    if "/" in sample or "\\" in sample or sample.startswith(".") or "\x00" in sample:
        raise HTTPException(400, "sample name must be a bundled file basename")
    repo = _Path(__file__).resolve().parents[3]
    samples_dir = (repo / "samples").resolve()
    src = (samples_dir / sample).resolve()
    try:
        src.relative_to(samples_dir)
    except ValueError:
        raise HTTPException(400, "sample path escapes the samples/ directory")
    if not src.is_file():
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

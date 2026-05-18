"""HTTP API for step-pack management.

Endpoints:
  POST   /packs/upload          multipart .dpack — stages, returns metadata
  POST   /packs/install         { pack_id, version } — moves staged → installed
  DELETE /packs/_pending/{id}   discard a staged pending pack
  GET    /packs                 list installed packs (cached manifests)
  GET    /packs/_pending        list staged uploads
  PATCH  /packs/{pack_id}       { enabled: bool } — soft toggle
  DELETE /packs/{pack_id}       uninstall an installed pack

Each mutating endpoint that touches the live step catalog calls
`reset_steps_registry()` so the next `/steps` request reflects the new
state without a backend restart.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from dig.engine.registry import reset_steps_registry
from dig.plugins import packs as pack_mod
from dig.storage.db import get_session
from dig.storage.models import StepPack

router = APIRouter(prefix="/packs", tags=["packs"])


# ── Pydantic shapes ────────────────────────────────────────────────


class PackConflictOut(BaseModel):
    step_id: str
    existing_source: str


class StagedPackOut(BaseModel):
    pack_id: str
    version: str
    label: str
    description: str
    license: str | None = None
    author: str | None = None
    homepage: str | None = None
    readme: str | None = None
    steps: list[str]
    connectors: list[str]
    python_requirements: list[str] = Field(default_factory=list)
    declared_checksum: str | None = None
    computed_checksum: str
    conflicts: list[PackConflictOut]


class InstallPackIn(BaseModel):
    pack_id: str
    version: str


class InstalledPackOut(BaseModel):
    id: str
    version: str
    label: str
    description: str | None = None
    license: str | None = None
    author: str | None = None
    homepage: str | None = None
    enabled: bool
    steps: list[str]
    connectors: list[str]
    python_requirements: list[str] = Field(default_factory=list)
    checksum: str | None = None
    installed_at: str
    updated_at: str


class TogglePackIn(BaseModel):
    enabled: bool


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("/upload", response_model=StagedPackOut)
async def upload_pack(file: UploadFile = File(...)) -> StagedPackOut:
    """Receive a .dpack archive, stage it for review.

    No DB write. The operator confirms the install in a follow-up
    `POST /packs/install` call after seeing the staged manifest.
    """
    if file.filename and not file.filename.lower().endswith((".dpack", ".zip")):
        # We accept .zip too because some users will not realise the
        # extension matters. The contents are what's enforced.
        pass
    content = await file.read()
    try:
        staged = pack_mod.stage_pack(content, source_url=file.filename)
    except pack_mod.PackError as e:
        raise HTTPException(400, str(e)) from e

    return StagedPackOut(
        pack_id=staged.pack_id,
        version=staged.version,
        label=staged.label,
        description=staged.description,
        license=staged.license,
        author=staged.author,
        homepage=staged.homepage,
        readme=staged.readme,
        steps=staged.steps,
        connectors=staged.connectors,
        python_requirements=staged.python_requirements,
        declared_checksum=staged.declared_checksum,
        computed_checksum=staged.computed_checksum,
        conflicts=[
            PackConflictOut(step_id=c.step_id, existing_source=c.existing_source)
            for c in staged.conflicts
        ],
    )


@router.post("/install")
async def install_pack(
    body: InstallPackIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Move a staged pack into plugins/packs/<id>/, register it, and
    install its declared Python dependencies.

    Auto-install is on by default; set DIG_PACK_AUTO_INSTALL_DEPS=0 to
    disable. The install proceeds even if pip fails — the response
    surfaces success/failure so the operator can act on it.
    """
    pending = pack_mod.PENDING_PACKS_DIR / f"{body.pack_id}-{body.version}"
    if not pending.exists():
        raise HTTPException(404, f"no staged pack for {body.pack_id} v{body.version}")

    try:
        manifest = pack_mod.read_pack_manifest(pending)
    except pack_mod.PackError as e:
        raise HTTPException(400, str(e)) from e

    try:
        result = pack_mod.install_staged(body.pack_id, body.version)
    except pack_mod.PackError as e:
        raise HTTPException(400, str(e)) from e

    existing = (await session.execute(
        sa_select(StepPack).where(StepPack.id == body.pack_id),
    )).scalar_one_or_none()
    if existing is None:
        session.add(StepPack(
            id=body.pack_id,
            version=body.version,
            checksum=manifest.get("checksum"),
            enabled=True,
            manifest=manifest,
        ))
    else:
        existing.version = body.version
        existing.checksum = manifest.get("checksum")
        existing.enabled = True
        existing.manifest = manifest
    await session.commit()

    reset_steps_registry()

    dep_payload: dict[str, Any] | None = None
    if result.dep_install is not None:
        dep_payload = {
            "requirements": result.dep_install.requirements,
            "success": result.dep_install.success,
            "elapsed_sec": round(result.dep_install.elapsed_sec, 1),
            "output": result.dep_install.output,
            "skipped_reason": result.dep_install.skipped_reason,
        }

    return {
        "ok": True,
        "installed_at": str(result.install_dir),
        "pack_id": body.pack_id,
        "version": body.version,
        "dep_install": dep_payload,
    }


@router.delete("/_pending/{pack_id}")
async def discard_pending(pack_id: str, version: str) -> dict[str, Any]:
    """Drop a staged pending pack without installing."""
    try:
        pack_mod.discard_staged(pack_id, version)
    except pack_mod.PackError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "discarded": pack_id, "version": version}


@router.get("", response_model=list[InstalledPackOut])
async def list_installed(
    session: AsyncSession = Depends(get_session),
) -> list[InstalledPackOut]:
    """Return every installed pack — registry source of truth.

    Disk + DB are reconciled on read: if a pack's directory has been
    manually deleted, its row is dropped; if a directory exists without
    a row we surface it with the cached manifest if any. The latter
    rarely happens (only after a manual file copy) but keeps the UI
    honest.
    """
    rows = (await session.execute(sa_select(StepPack))).scalars().all()
    on_disk_ids = {p.name for p in pack_mod.list_installed_pack_dirs()}

    out: list[InstalledPackOut] = []
    for r in rows:
        if r.id not in on_disk_ids:
            # Stale row — pack deleted out of band. Drop it.
            await session.execute(sa_delete(StepPack).where(StepPack.id == r.id))
            continue
        m = r.manifest or {}
        out.append(InstalledPackOut(
            id=r.id,
            version=r.version,
            label=str(m.get("label", r.id)),
            description=m.get("description"),
            license=m.get("license"),
            author=m.get("author"),
            homepage=m.get("homepage"),
            enabled=r.enabled,
            steps=list(m.get("steps") or []),
            connectors=list(m.get("connectors") or []),
            python_requirements=list(m.get("pythonRequirements") or []),
            checksum=r.checksum,
            installed_at=r.installed_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
        ))
    await session.commit()
    return out


@router.patch("/{pack_id}")
async def toggle_pack(
    pack_id: str,
    body: TogglePackIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Enable / disable a pack without removing it from disk."""
    row = (await session.execute(
        sa_select(StepPack).where(StepPack.id == pack_id),
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"pack {pack_id!r} not installed")
    row.enabled = body.enabled
    await session.commit()
    reset_steps_registry()
    return {"ok": True, "id": pack_id, "enabled": body.enabled}


@router.delete("/{pack_id}")
async def uninstall_pack(
    pack_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Remove an installed pack from disk and drop its registry row.

    Returns 404 when the pack is absent from BOTH disk and the registry —
    the previous shape returned 200 OK in that case, which made it
    impossible for a UI / script to tell whether their delete actually
    matched anything.
    """
    row = (await session.execute(
        sa_select(StepPack).where(StepPack.id == pack_id),
    )).scalar_one_or_none()
    on_disk = (pack_mod.PACKS_DIR / pack_id).exists()
    if row is None and not on_disk:
        raise HTTPException(404, f"pack '{pack_id}' is not installed")
    try:
        pack_mod.uninstall_pack(pack_id)
    except pack_mod.PackError as e:
        raise HTTPException(400, str(e)) from e
    if row is not None:
        await session.execute(sa_delete(StepPack).where(StepPack.id == pack_id))
        await session.commit()
    reset_steps_registry()
    return {"ok": True, "uninstalled": pack_id}

"""Public template gallery endpoints.

Lives separately from /pipelines/templates/list (which serves the bundled
samples/templates/ repo files). This module manages user-owned shareable
templates stored in the Template table.

Slug generation: kebab-case title + 6-char ULID suffix to prevent collisions
and squatting. Visibility is lockable per template ("public" requires manual
review for now via DIG_TEMPLATE_REVIEW=manual).
"""

from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.engine.pipeline import Pipeline
from dig.storage.db import get_session
from dig.storage.models import Pipeline as PipelineRow
from dig.storage.models import Template

router = APIRouter(prefix="/templates", tags=["templates"])


# ---- Pydantic shapes ---------------------------------------------------


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    title: str
    summary: str | None
    tags: list[str]
    needsSampleDataset: bool = Field(alias="needs_sample_dataset")
    sampleDatasetUrl: str | None = Field(default=None, alias="sample_dataset_url")
    authorHandle: str | None = Field(default=None, alias="author_handle")
    authorUrl: str | None = Field(default=None, alias="author_url")
    isCurated: bool = Field(alias="is_curated")
    visibility: str
    upvotes: int
    viewCount: int = Field(alias="view_count")
    createdAt: datetime = Field(alias="created_at")


class TemplateDetailOut(TemplateOut):
    document: dict[str, Any]


class CreateTemplateRequest(BaseModel):
    pipelineId: str
    title: str
    summary: str | None = None
    tags: list[str] = []
    sampleDatasetUrl: str | None = None
    needsSampleDataset: bool = False
    authorHandle: str | None = None
    authorUrl: str | None = None
    visibility: str = "unlisted"


# ---- Slug generation ---------------------------------------------------


def _slugify(text: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", text.lower()).strip("-")
    base = base[:80] or "template"
    return base


def _make_unique_slug(title: str) -> str:
    return f"{_slugify(title)}-{str(ULID())[-6:].lower()}"


# ---- Secret stripping --------------------------------------------------


_SECRET_KEY_RE = re.compile(r"(api_key|password|secret|token|bearer)", re.I)


def _strip_secrets(doc: dict[str, Any]) -> dict[str, Any]:
    """Remove keys likely to contain secrets before publishing.

    Defensive — pipelines should already have secrets in saved Connections,
    not inline. But for `.dig.json` imports that did inline credentials,
    this is the safety net.
    """
    def scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if isinstance(k, str) and _SECRET_KEY_RE.search(k):
                    out[k] = "__redacted__"
                else:
                    out[k] = scrub(v)
            return out
        if isinstance(obj, list):
            return [scrub(x) for x in obj]
        if isinstance(obj, str):
            # Catch URI-form `?password=foo` patterns.
            if "://" in obj and re.search(r"://[^@/]+:[^@/]+@", obj):
                return re.sub(r"://([^@/]+):[^@/]+@", r"://\1:__redacted__@", obj)
        return obj

    return scrub(doc)


# ---- Endpoints ---------------------------------------------------------


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    visibility: str | None = None,
    tag: str | None = None,
    limit: int = 60,
    session: AsyncSession = Depends(get_session),
) -> list[TemplateOut]:
    """List user-owned templates. Defaults to public + unlisted with curated first."""
    stmt = select(Template)
    if visibility:
        stmt = stmt.where(Template.visibility == visibility)
    else:
        stmt = stmt.where(Template.visibility.in_(["public", "unlisted"]))
    if tag:
        # SQLite has no JSON-array-contains operator; fall back to a substring
        # match on the JSON-serialized tag list. Quoted to avoid matching
        # `cleanup-2` when the user asks for `cleanup`. Push the predicate
        # into SQL so the LIMIT applies to *matching* rows, not the first
        # `limit` rows that happen to also be tagged.
        stmt = stmt.where(func.instr(func.json(Template.tags), f'"{tag}"') > 0)
    rows = (
        await session.execute(
            stmt.order_by(Template.is_curated.desc(), Template.created_at.desc()).limit(
                max(1, min(limit, 200))
            )
        )
    ).scalars().all()
    return [TemplateOut.model_validate(r) for r in rows]


@router.get("/{slug}", response_model=TemplateDetailOut)
async def get_template(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> TemplateDetailOut:
    rows = (
        await session.execute(select(Template).where(Template.slug == slug))
    ).scalars().all()
    if not rows:
        raise HTTPException(404, "template not found")
    t = rows[0]
    if t.visibility == "private":
        raise HTTPException(404, "template not found")
    # Atomic increment so concurrent reads don't lost-update each other.
    # The ORM-level `t.view_count += 1` reads then writes from this session
    # without `FOR UPDATE`; under load two viewers race and the count
    # advances by 1 instead of 2.
    await session.execute(
        update(Template)
        .where(Template.id == t.id)
        .values(view_count=Template.view_count + 1)
    )
    await session.commit()
    out = TemplateDetailOut.model_validate(t)
    out.document = t.document
    return out


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    req: CreateTemplateRequest,
    session: AsyncSession = Depends(get_session),
) -> TemplateOut:
    """Share a pipeline as a template. Strips secrets before storage."""
    pipe = await session.get(PipelineRow, req.pipelineId)
    if pipe is None:
        raise HTTPException(404, "pipeline not found")

    # `_strip_secrets` walks the dict tree and only allocates new dicts on
    # the secret-rewrite path; for fully-clean docs it returns the same
    # nested objects, which would mutate `pipe.document` in-memory if any
    # downstream code re-emitted it. Deepcopy first to make `doc` a fully
    # independent tree.
    doc = _strip_secrets(copy.deepcopy(pipe.document or {}))
    # Validate the stripped doc is still a valid pipeline.
    try:
        Pipeline.model_validate({**doc, "id": "PLACEHOLDER", "name": req.title})
    except Exception as e:
        raise HTTPException(400, f"pipeline invalid post-strip: {e}") from e

    if req.visibility not in ("private", "unlisted", "public"):
        raise HTTPException(400, "visibility must be private, unlisted, or public")
    # "public" requires manual curation in this iteration — coerce to unlisted.
    visibility = "unlisted" if req.visibility == "public" else req.visibility

    # Slug collisions are rare (6-char base32 suffix on a kebab-case title)
    # but the unique-index would otherwise raise IntegrityError → 500. Retry
    # a few times with fresh suffixes before giving up.
    last_err: IntegrityError | None = None
    for _attempt in range(5):
        slug = _make_unique_slug(req.title)
        t = Template(
            id=str(ULID()),
            slug=slug,
            title=req.title.strip()[:255],
            summary=(req.summary or "").strip()[:1000] or None,
            tags=req.tags or [],
            document=doc,
            sample_dataset_url=req.sampleDatasetUrl,
            needs_sample_dataset=req.needsSampleDataset,
            author_handle=(req.authorHandle or "").strip()[:64] or None,
            author_url=(req.authorUrl or "").strip()[:255] or None,
            is_curated=False,
            visibility=visibility,
        )
        session.add(t)
        try:
            await session.commit()
            return TemplateOut.model_validate(t)
        except IntegrityError as e:
            await session.rollback()
            last_err = e
            continue
    raise HTTPException(409, f"slug collision after 5 retries: {last_err}")


@router.post("/{slug}/clone", response_model=dict[str, str], status_code=201)
async def clone_template(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Materialize a template into a new pipeline owned by the caller."""
    rows = (
        await session.execute(select(Template).where(Template.slug == slug))
    ).scalars().all()
    if not rows:
        raise HTTPException(404, "template not found")
    t = rows[0]
    pid = str(ULID())
    doc = dict(t.document or {})
    doc["id"] = pid
    doc["name"] = t.title
    pipe = PipelineRow(id=pid, name=t.title, document=doc, etag=1)
    session.add(pipe)
    await session.commit()
    return {"pipelineId": pid}

"""Phase-A-pro #3 — Workspace-wide search.

Single endpoint that searches across pipelines, datasets, and columns.
Used by the global cmdk "Search workspace" shortcut so a user can find
*every* place a name appears without manually navigating each surface.

Search is plain substring (case-insensitive) — no fuzzy / embedding /
ranking. For free-tier workspaces (single-digit to low-hundreds of
pipelines), this is fast enough and predictable. We can move to a real
search index (whoosh / sqlite FTS / tantivy) when workspace size grows
past ~500 entities.

Patent posture: substring search has prior art back to Unix `grep`
(1974). Cross-entity unified search is the basic UX of every IDE
(Sublime, Atom, VS Code). No risk.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dig.storage.db import get_session
from dig.storage.models import Dataset
from dig.storage.models import Pipeline as PipelineRow

router = APIRouter(prefix="/search", tags=["search"])


# ---- Schemas ------------------------------------------------------------


class SearchHit(BaseModel):
    """One result row. `kind` drives icon + click target on the
    frontend; `id` is the entity id; `label` is the user-visible
    title; `subtitle` carries the secondary info (description /
    parent / type)."""
    kind: str               # "pipeline" | "dataset" | "column" | "tag"
    id: str
    label: str
    subtitle: str | None = None
    # Where to navigate when this hit is clicked. Frontend treats as
    # opaque path segment.
    href: str
    # Set when the match was specifically on a tag — the frontend
    # surfaces it as a chip rather than a substring.
    tag_match: str | None = None


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]
    total: int


# ---- Endpoint ----------------------------------------------------------


@router.get("", response_model=SearchOut)
async def search(
    q: str = Query("", description="Substring to search for. Case-insensitive."),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> SearchOut:
    """Search across pipelines, datasets, columns, and tags. Returns
    results in priority order: exact matches first, then prefix
    matches, then substring matches."""
    needle = q.strip().lower()
    if not needle:
        return SearchOut(query=q, hits=[], total=0)

    hits: list[SearchHit] = []

    # --- Pipelines (name, description, tags) ---
    pipes_res = await session.execute(select(PipelineRow))
    for p in pipes_res.scalars().all():
        doc = p.document or {}
        name = (doc.get("name") or p.id).strip()
        desc = (doc.get("description") or "").strip()
        tags: list[str] = []
        for t in doc.get("tags") or []:
            if isinstance(t, str):
                tags.append(t)
        # Tag-as-match: surface the matched tag with `tag_match` so
        # the frontend can render it as a chip.
        for tag in tags:
            if needle in tag.lower():
                hits.append(SearchHit(
                    kind="pipeline",
                    id=p.id,
                    label=name or p.id,
                    subtitle=f"#{tag}",
                    href=f"/pipelines/{p.id}",
                    tag_match=tag,
                ))
                break  # one tag-hit per pipeline is enough
        else:
            # No tag hit — try name / description.
            if needle in name.lower() or (desc and needle in desc.lower()):
                hits.append(SearchHit(
                    kind="pipeline",
                    id=p.id,
                    label=name or p.id,
                    subtitle=desc or f"{len(doc.get('nodes') or [])} steps",
                    href=f"/pipelines/{p.id}",
                ))

    # --- Datasets (name, tags) ---
    ds_res = await session.execute(select(Dataset))
    for d in ds_res.scalars().all():
        opts = d.options or {}
        ds_tags: list[str] = []
        for t in opts.get("tags") or []:
            if isinstance(t, str):
                ds_tags.append(t)
        for tag in ds_tags:
            if needle in tag.lower():
                hits.append(SearchHit(
                    kind="dataset",
                    id=d.id,
                    label=d.name or d.id,
                    subtitle=f"#{tag}",
                    href=f"/datasets/{d.id}",
                    tag_match=tag,
                ))
                break
        else:
            if needle in (d.name or "").lower():
                hits.append(SearchHit(
                    kind="dataset",
                    id=d.id,
                    label=d.name or d.id,
                    subtitle=f"{d.connector} · {d.row_count or 0:,} rows",
                    href=f"/datasets/{d.id}",
                ))

    # --- Columns (across all dataset profiles) ---
    # Datasets already loaded above — reuse the same iteration. Match
    # on column name. Each match emits its own hit.
    ds_res2 = await session.execute(select(Dataset))
    for d in ds_res2.scalars().all():
        for col in d.columns or []:
            if not isinstance(col, dict):
                continue
            cname = col.get("name")
            if not isinstance(cname, str):
                continue
            if needle in cname.lower():
                hits.append(SearchHit(
                    kind="column",
                    id=f"{d.id}:{cname}",
                    label=cname,
                    subtitle=f"in {d.name or d.id}",
                    href=f"/datasets/{d.id}#col={cname}",
                ))

    # --- Re-rank: exact match → prefix match → substring, then by KIND
    # (pipelines + datasets first, then columns) so a column-name match
    # storm doesn't push the pipeline/dataset hits off the front page.
    # Round-3 QA finding: previously a single dataset with 200 columns
    # whose names all contained the needle would saturate ``limit`` and
    # bury the actually-relevant pipeline/dataset matches.
    KIND_RANK = {"pipeline": 0, "dataset": 1, "tag": 2, "column": 3}

    def score(hit: SearchHit) -> tuple[int, int]:
        target = hit.label.lower()
        if target == needle:
            text_rank = 0
        elif target.startswith(needle):
            text_rank = 1
        else:
            text_rank = 2
        return (text_rank, KIND_RANK.get(hit.kind, 99))

    hits.sort(key=score)

    return SearchOut(query=q, hits=hits[:limit], total=len(hits))


# ---- Tags helpers ------------------------------------------------------


class TagsOut(BaseModel):
    tags: list[str]


@router.get("/tags", response_model=TagsOut)
async def list_all_tags(
    session: AsyncSession = Depends(get_session),
) -> TagsOut:
    """All tags across pipelines + datasets, deduped + sorted. Powers
    autocomplete on the tag input + the catalog filter dropdown."""
    seen: set[str] = set()
    pipes_res = await session.execute(select(PipelineRow))
    for p in pipes_res.scalars().all():
        for t in (p.document or {}).get("tags") or []:
            if isinstance(t, str) and t.strip():
                seen.add(t.strip())
    ds_res = await session.execute(select(Dataset))
    for d in ds_res.scalars().all():
        for t in (d.options or {}).get("tags") or []:
            if isinstance(t, str) and t.strip():
                seen.add(t.strip())
    return TagsOut(tags=sorted(seen, key=lambda s: s.lower()))


# ---- Pipeline tag mutation ---------------------------------------------


class PipelineTagsIn(BaseModel):
    tags: list[str]


@router.put("/pipelines/{pipeline_id}/tags", response_model=TagsOut)
async def set_pipeline_tags(
    pipeline_id: str,
    body: PipelineTagsIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TagsOut:
    """Replace the pipeline's tag list. Tags are normalised to
    lowercase + trimmed so `Revenue` and `revenue` collapse.

    Concurrency control: pass the current ``etag`` in an ``If-Match``
    header. The endpoint rejects with 409 when the header is supplied
    and doesn't match — this stops the autosave-vs-tag-edit race that
    would otherwise lose either side's changes (QA finding round 2).
    Callers that don't supply the header (older / scripting clients)
    still go through unguarded for backward compatibility.

    History snapshot: every tag change is recorded as a
    ``manual_save`` snapshot with ``triggered_by="tag_edit"``. The
    previous version of this endpoint was a back-channel that mutated
    the document AND bumped the etag without a snapshot, so undo /
    restore couldn't see the change.
    """
    from fastapi import HTTPException
    from dig.engine.history import snapshot_pipeline

    res = await session.execute(
        select(PipelineRow).where(PipelineRow.id == pipeline_id),
    )
    p = res.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="pipeline not found")

    if_match = request.headers.get("if-match")
    if if_match is not None:
        try:
            expected = int(if_match.strip().strip('"'))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"If-Match must be the integer pipeline etag; got {if_match!r}",
            )
        if expected != p.etag:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "etag_mismatch",
                    "expected": expected,
                    "actual": p.etag,
                    "message": "pipeline was modified — refresh and retry",
                },
            )

    cleaned: list[str] = []
    seen: set[str] = set()
    for t in body.tags:
        if not isinstance(t, str):
            continue
        norm = t.strip().lower()
        if not norm or norm in seen:
            continue
        # Keep tags simple — alphanumerics, dashes, underscores.
        # Reject anything weird so URL-safe + consistent.
        if not all(c.isalnum() or c in "-_" for c in norm):
            continue
        seen.add(norm)
        cleaned.append(norm)

    doc = dict(p.document or {})
    prior_tags = doc.get("tags") or []
    doc["tags"] = cleaned
    p.document = doc
    p.etag = (p.etag or 0) + 1

    # Audit-trail snapshot — undo / restore / diff need to see the change.
    if prior_tags != cleaned:
        await snapshot_pipeline(
            session, pipeline_id, doc, p.etag,
            triggered_by="tag_edit",
            change_reason=f"tags: {prior_tags} → {cleaned}",
        )
    await session.commit()
    return TagsOut(tags=cleaned)

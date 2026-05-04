"""Pipeline history snapshotting + retention.

Helpers used by the pipelines router on save / run-start / import / restore.
Kept separate from `diff.py` (pure functions) so the SQLAlchemy bits don't
leak into the diff algorithm — diff stays unit-testable in isolation.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.engine.diff import diff_pipelines, document_hash
from dig.storage.models import PipelineHistory


def _max_snapshots() -> int:
    raw = os.environ.get("DIG_PIPELINE_HISTORY_MAX", "50")
    try:
        n = int(raw)
        return max(2, n)
    except ValueError:
        return 50


async def _latest_snapshot(
    session: AsyncSession, pipeline_id: str
) -> PipelineHistory | None:
    rows = (
        await session.execute(
            select(PipelineHistory)
            .where(PipelineHistory.pipeline_id == pipeline_id)
            .order_by(PipelineHistory.created_at.desc())
            .limit(1)
        )
    ).scalars().all()
    return rows[0] if rows else None


async def _trim_history(session: AsyncSession, pipeline_id: str, keep: int) -> None:
    """Keep only the `keep` most recent snapshots for this pipeline."""
    # Use a correlated subquery so the keeper-set lives in SQL and the planner
    # can reason about it. The previous shape pulled `keep` ULIDs into Python
    # and round-tripped them as a `notin_(...)` parameter list — fine at the
    # default of 50, but unbounded once `DIG_PIPELINE_HISTORY_MAX` is raised.
    keep_subq = (
        select(PipelineHistory.id)
        .where(PipelineHistory.pipeline_id == pipeline_id)
        .order_by(PipelineHistory.created_at.desc())
        .limit(keep)
    ).scalar_subquery()
    await session.execute(
        delete(PipelineHistory).where(
            PipelineHistory.pipeline_id == pipeline_id,
            PipelineHistory.id.notin_(keep_subq),
        )
    )


async def snapshot_pipeline(
    session: AsyncSession,
    pipeline_id: str,
    document: dict[str, Any],
    etag: int,
    triggered_by: str,
    change_reason: str | None = None,
    run_id: str | None = None,
) -> PipelineHistory | None:
    """Snapshot a pipeline document.

    No-ops when the document is unchanged from the most recent snapshot
    (deduped by hash). Returns the newly-created snapshot, or None if a
    duplicate was suppressed.

    Pass `run_id` for `triggered_by="run_start"` snapshots so the diff
    endpoint can resolve `run:<id>` refs by column lookup instead of by
    grovelling for a key that was never written into the document.
    """
    h = document_hash(document)
    latest = await _latest_snapshot(session, pipeline_id)
    if latest and latest.document_hash == h:
        return None

    summary: str | None = None
    if latest is not None:
        d = diff_pipelines(latest.document, document)
        summary = d["summary"]

    snap = PipelineHistory(
        id=str(ULID()),
        pipeline_id=pipeline_id,
        document=document,
        etag=etag,
        change_summary=summary,
        change_reason=change_reason,
        triggered_by=triggered_by,
        document_hash=h,
        run_id=run_id,
    )
    session.add(snap)
    # Caller owns commit semantics so this co-mingles with the actual mutation.
    await _trim_history(session, pipeline_id, _max_snapshots())
    return snap

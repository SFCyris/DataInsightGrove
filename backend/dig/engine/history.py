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
    """Trim pipeline history with two retention budgets:

      - **Autosaves** (`triggered_by='autosave'`): only the 5 most recent.
        The crash-recovery use case doesn't need a long tail; without this,
        a few minutes of typing through 60 autosaves would push every
        labeled checkpoint out of the window.
      - **Everything else** (manual_save / run_start / import / restore):
        up to `keep` recent. These carry user intent so we treat them as
        first-class.

    Implemented as two independent DELETEs because SQLite rejects
    `UNION` over `SELECT … ORDER BY … LIMIT` inside a `NOT IN` subquery.
    Each category has its own keep-set carved out by a correlated
    sub-query, which the planner handles cleanly.
    """
    # 1. Trim autosaves to 5 most recent.
    autosave_keep_subq = (
        select(PipelineHistory.id)
        .where(
            PipelineHistory.pipeline_id == pipeline_id,
            PipelineHistory.triggered_by == "autosave",
        )
        .order_by(PipelineHistory.created_at.desc())
        .limit(5)
    ).scalar_subquery()
    await session.execute(
        delete(PipelineHistory).where(
            PipelineHistory.pipeline_id == pipeline_id,
            PipelineHistory.triggered_by == "autosave",
            PipelineHistory.id.notin_(autosave_keep_subq),
        )
    )

    # 2. Trim everything-else (manual_save, run_start, import, restore) to `keep`.
    other_keep_subq = (
        select(PipelineHistory.id)
        .where(
            PipelineHistory.pipeline_id == pipeline_id,
            PipelineHistory.triggered_by != "autosave",
        )
        .order_by(PipelineHistory.created_at.desc())
        .limit(keep)
    ).scalar_subquery()
    await session.execute(
        delete(PipelineHistory).where(
            PipelineHistory.pipeline_id == pipeline_id,
            PipelineHistory.triggered_by != "autosave",
            PipelineHistory.id.notin_(other_keep_subq),
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
    # Round-4 QA finding: ``PipelineHistory.document`` is a JSON column
    # with no size cap. A pipeline doc with megabyte-sized params (e.g.
    # a malformed import) was re-snapshotted on every save / run start,
    # so the row stack could grow to tens of MB and slow every
    # list-pipelines query. Cap defensively — anything above this is
    # operationally suspect.
    import json as _json_for_size
    encoded = _json_for_size.dumps(document, default=str)
    _MAX_SNAPSHOT_BYTES = 512 * 1024  # 512 KiB
    if len(encoded) > _MAX_SNAPSHOT_BYTES:
        raise ValueError(
            f"pipeline document is {len(encoded):,} bytes; refusing to "
            f"snapshot (max {_MAX_SNAPSHOT_BYTES:,}). Trim large step "
            "parameters before saving.",
        )
    h = document_hash(document)
    latest = await _latest_snapshot(session, pipeline_id)
    # Dedup by document hash for transient triggers (autosave / run_start),
    # but always record explicit user actions ("manual_save" with a label,
    # imports, restores) — these carry intent that the hash alone doesn't
    # express. Without the carve-out, a Save-with-label right after an
    # autosave would silently drop the label.
    if latest and latest.document_hash == h:
        explicit = triggered_by in ("manual_save", "import", "restore")
        # For manual_save with no reason and identical bytes, still dedup —
        # otherwise hammering the Save button would create stacks of empty
        # checkpoints that aren't useful.
        if not (explicit and (change_reason or triggered_by != "manual_save")):
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
    # Flush so the new row participates in the keep-set selection — without
    # this, `_trim_history` runs against `keep` *existing* rows, then the
    # new add goes through commit and the table ends up with `keep+1` rows.
    await session.flush()
    # Caller owns commit semantics so this co-mingles with the actual mutation.
    await _trim_history(session, pipeline_id, _max_snapshots())
    return snap

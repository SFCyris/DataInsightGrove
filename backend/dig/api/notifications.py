"""Notifications API — append-only event log surfaced in /settings.

Currently emits events from a small set of internal triggers (pipeline run
failure is the first); future deliveries (email, syslog, webhook) read from
this same store. Every event has a stable shape — date, kind, level,
title, message, user, context — so downstream channels can fan out without
changing producers.

Three resources:
  - GET    /notifications              List, filterable by kind/level + paginated
  - GET    /notifications/unread-count Tiny endpoint for the bell badge
  - PATCH  /notifications/{id}/dismiss Soft-dismiss a single row
  - POST   /notifications/dismiss-all  Soft-dismiss all undismissed
  - DELETE /notifications/{id}         Hard-delete (removes from the audit log)

Producers call `record_notification()` — a small async helper that opens
its own session so it can be invoked from anywhere in the API process,
including background workers that don't already have a session in scope.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.storage.db import SessionLocal, get_session
from dig.storage.models import Notification

log = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---- Vocabulary ---------------------------------------------------------

# Accepted kinds. Free-form on the model; constrained here so the UI's
# filter dropdown stays meaningful and downstream channels can route on
# kind without a long if-chain. Adding a new kind is a one-line change
# but should be a deliberate one.
_KINDS: tuple[str, ...] = (
    "system",       # server lifecycle, generic backend errors
    "runtime",      # pipeline run lifecycle (queued, succeeded, failed)
    "freshness",    # SLA/freshness threshold breaches
    "login",        # auth events (Phase B+ when auth lands)
    "resources",    # disk space, OOM, rate limits
    "security",     # auth-token violations, suspicious requests
)
NotificationKind = Literal[
    "system", "runtime", "freshness", "login", "resources", "security",
]
NotificationLevel = Literal["notification", "warning", "error"]


# ---- Schemas ------------------------------------------------------------


class NotificationOut(BaseModel):
    """Single notification, as returned by GET /notifications."""
    id: str
    createdAt: datetime
    kind: str
    level: str
    title: str
    message: str | None = None
    userId: str | None = None
    context: dict[str, Any] | None = None
    dismissedAt: datetime | None = None


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int           # total matching the filter, for pagination
    unread: int          # convenience: count where dismissed_at IS NULL


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        createdAt=n.created_at,
        kind=n.kind,
        level=n.level,
        title=n.title,
        message=n.message,
        userId=n.user_id,
        context=n.context,
        dismissedAt=n.dismissed_at,
    )


# ---- Producer helper ----------------------------------------------------


async def record_notification(
    *,
    kind: NotificationKind | str,
    level: NotificationLevel | str = "notification",
    title: str,
    message: str | None = None,
    user_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Persist one notification.

    Designed to be safe to call from anywhere — opens its own session,
    swallows errors so a notification failure never breaks the
    triggering operation. Returns the new ULID for any caller that
    wants to follow up.
    """
    if kind not in _KINDS:
        log.warning("notification kind %r not in vocabulary; allowing anyway", kind)
    if level not in ("notification", "warning", "error"):
        log.warning("notification level %r not recognised; defaulting to notification", level)
        level = "notification"

    nid = str(ULID())
    try:
        async with SessionLocal() as session:
            session.add(Notification(
                id=nid,
                kind=str(kind),
                level=str(level),
                title=title,
                message=message,
                user_id=user_id,
                context=context,
            ))
            await session.commit()
        log.debug("recorded notification %s [%s/%s] %r", nid, kind, level, title)
    except Exception:
        # Never let notification persistence break a real operation. If the
        # DB is down, log it and move on — the triggering caller has its
        # own error path.
        log.exception("failed to record notification [%s/%s] %r", kind, level, title)
    return nid


# ---- Endpoints ----------------------------------------------------------


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    session: AsyncSession = Depends(get_session),
    kind: str | None = Query(None, description="Filter by notification kind"),
    level: str | None = Query(None, description="Filter by level"),
    include_dismissed: bool = Query(False, description="Include soft-dismissed rows"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> NotificationListOut:
    """List notifications, newest first. Pagination via limit/offset."""
    base_q = select(Notification)
    count_q = select(func.count()).select_from(Notification)
    if kind:
        base_q = base_q.where(Notification.kind == kind)
        count_q = count_q.where(Notification.kind == kind)
    if level:
        base_q = base_q.where(Notification.level == level)
        count_q = count_q.where(Notification.level == level)
    if not include_dismissed:
        base_q = base_q.where(Notification.dismissed_at.is_(None))
        count_q = count_q.where(Notification.dismissed_at.is_(None))

    rows_res = await session.execute(
        base_q.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    )
    items = [_to_out(n) for n in rows_res.scalars().all()]

    # Round-9 fix: COUNT(*) at SQL layer instead of loading every id
    # into Python and len()ing it — same indexes, O(1) memory.
    total = int((await session.execute(count_q)).scalar() or 0)
    unread = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.dismissed_at.is_(None))
            )
        ).scalar()
        or 0
    )

    return NotificationListOut(items=items, total=total, unread=unread)


@router.get("/unread-count")
async def unread_count(session: AsyncSession = Depends(get_session)) -> dict[str, int]:
    """Tiny endpoint for the header bell badge — uses COUNT(*) at the
    SQL layer (Round-9 fix: was loading every id and len()ing it)."""
    res = await session.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.dismissed_at.is_(None))
    )
    return {"unread": int(res.scalar() or 0)}


@router.patch("/{notification_id}/dismiss", response_model=NotificationOut)
async def dismiss_notification(
    notification_id: str, session: AsyncSession = Depends(get_session)
) -> NotificationOut:
    """Soft-dismiss: mark dismissed_at, keep the row for audit."""
    n = await session.get(Notification, notification_id)
    if n is None:
        raise HTTPException(404, "notification not found")
    if n.dismissed_at is None:
        from datetime import timezone
        n.dismissed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(n)
    return _to_out(n)


@router.post("/dismiss-all", response_model=dict)
async def dismiss_all_notifications(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Soft-dismiss every currently-undismissed notification."""
    from datetime import timezone
    now = datetime.now(timezone.utc)
    res = await session.execute(
        update(Notification)
        .where(Notification.dismissed_at.is_(None))
        .values(dismissed_at=now)
    )
    await session.commit()
    return {"dismissed": res.rowcount or 0}


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    """Hard-delete: removes from the audit log. Use with care."""
    res = await session.execute(
        delete(Notification).where(Notification.id == notification_id)
    )
    if res.rowcount == 0:
        raise HTTPException(404, "notification not found")
    await session.commit()

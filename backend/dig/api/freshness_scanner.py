"""Phase A — periodic freshness scanner.

Walks every pipeline that has freshness policies declared (per-node OR
per-group), recomputes their state against the latest succeeded run,
and emits transition events when a state crosses a boundary
(fresh → due, due → stale, recovered).

Runs every SCAN_INTERVAL_SECONDS (default 60s) inside the API process
as a background asyncio task. Started + stopped via the FastAPI
lifespan in main.py.

Why scan vs push: in Phase A we don't have a real scheduler emitting
per-step run events as they finish, AND a node can transition to
"stale" purely by the wall clock advancing — no run event would fire
that. A periodic poll covers both cases without any new infrastructure.

The scanner uses the SAME state cache (_FRESHNESS_LAST_SEEN) as the
opportunistic emission path in pipelines.py's /freshness endpoint, so
we don't double-fire when both paths see the same transition.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from dig.api.events import EventKinds, emit_event
from dig.engine.freshness import compute_node_freshness
from dig.storage.db import SessionLocal
from dig.storage.models import Pipeline as PipelineRow
from dig.storage.models import Run

log = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 60


async def _scan_once() -> None:
    """One pass over every pipeline with declared freshness policies.

    Imported lazily inside so the per-process cache lives in the same
    module as the opportunistic path — no double-emission from both
    code paths racing on the same transition."""
    from dig.api.pipelines import _FRESHNESS_LAST_SEEN  # noqa: SLF001

    try:
        async with SessionLocal() as session:
            pipelines_res = await session.execute(select(PipelineRow))
            pipelines = list(pipelines_res.scalars().all())

            # Pre-fetch latest succeeded runs in one query (one per pipeline).
            runs_res = await session.execute(
                select(Run).where(Run.status == "succeeded").order_by(Run.finished_at.desc())
            )
            latest_run_by_pipeline: dict[str, Run] = {}
            for r in runs_res.scalars().all():
                if r.pipeline_id in latest_run_by_pipeline:
                    continue
                latest_run_by_pipeline[r.pipeline_id] = r

        for p in pipelines:
            doc = p.document or {}
            nodes = doc.get("nodes") or []
            groups = doc.get("groups") or []

            # Collect declared policies — same logic as the /freshness endpoint.
            node_decls: list[tuple[str, str, str | None, str]] = []  # (id, sla, warn, label)
            for n in nodes:
                ui = (n or {}).get("ui") or {}
                fr = ui.get("freshness") if isinstance(ui, dict) else None
                if isinstance(fr, dict) and fr.get("sla"):
                    label = ui.get("label") or n.get("step") or n["id"]
                    node_decls.append((n["id"], fr["sla"], fr.get("warn_at"), label))

            group_decls: list[tuple[str, str, str | None, str]] = []
            for g in groups:
                ui = (g or {}).get("ui") or {}
                fr = ui.get("freshness") if isinstance(ui, dict) else None
                if isinstance(fr, dict) and fr.get("sla"):
                    group_decls.append((g["id"], fr["sla"], fr.get("warn_at"), g.get("label", g["id"])))

            if not node_decls and not group_decls:
                continue

            run = latest_run_by_pipeline.get(p.id)
            last_run_at = run.finished_at if run else None
            last_run_iso = last_run_at.isoformat() if last_run_at else None

            for nid, sla, warn_at, label in node_decls:
                try:
                    state = compute_node_freshness(sla, warn_at, last_run_at)
                except ValueError:
                    state = "never"
                key = (p.id, "node", nid)
                prev = _FRESHNESS_LAST_SEEN.get(key)
                _FRESHNESS_LAST_SEEN[key] = state
                if prev is None or prev == state:
                    continue
                rank = {"fresh": 0, "due": 1, "stale": 2, "never": 0}
                if rank.get(state, 0) > rank.get(prev, 0):
                    kind = EventKinds.FRESHNESS_STALE if state == "stale" else EventKinds.FRESHNESS_DUE
                elif rank.get(state, 0) < rank.get(prev, 0):
                    kind = EventKinds.FRESHNESS_RECOVERED
                else:
                    continue
                await emit_event(
                    kind,
                    pipeline_id=p.id,
                    pipeline_name=doc.get("name") or p.id,
                    node_id=nid,
                    target_label=label,
                    target_kind="node",
                    previous_state=prev,
                    new_state=state,
                    sla=sla,
                    last_run_at=last_run_iso or "never",
                )

            for gid, sla, warn_at, label in group_decls:
                try:
                    state = compute_node_freshness(sla, warn_at, last_run_at)
                except ValueError:
                    state = "never"
                key = (p.id, "group", gid)
                prev = _FRESHNESS_LAST_SEEN.get(key)
                _FRESHNESS_LAST_SEEN[key] = state
                if prev is None or prev == state:
                    continue
                rank = {"fresh": 0, "due": 1, "stale": 2, "never": 0}
                if rank.get(state, 0) > rank.get(prev, 0):
                    kind = EventKinds.FRESHNESS_STALE if state == "stale" else EventKinds.FRESHNESS_DUE
                elif rank.get(state, 0) < rank.get(prev, 0):
                    kind = EventKinds.FRESHNESS_RECOVERED
                else:
                    continue
                await emit_event(
                    kind,
                    pipeline_id=p.id,
                    pipeline_name=doc.get("name") or p.id,
                    group_id=gid,
                    target_label=label,
                    target_kind="group",
                    previous_state=prev,
                    new_state=state,
                    sla=sla,
                    last_run_at=last_run_iso or "never",
                )

    except Exception:
        # Scanner failures must never crash the API process. Log and
        # let the next tick try again.
        log.exception("freshness scanner: scan_once failed")


async def _scanner_loop() -> None:
    log.info("freshness scanner: starting (every %ds)", SCAN_INTERVAL_SECONDS)
    while True:
        try:
            await _scan_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("freshness scanner loop iteration failed")
        # Sleep AFTER each scan; that way we get an immediate first pass.
        try:
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            log.info("freshness scanner: cancelled")
            raise


def start_freshness_scanner() -> asyncio.Task:
    """Returns the background task. Owner (lifespan) should hold the
    reference and cancel it on shutdown."""
    return asyncio.create_task(_scanner_loop(), name="dig-freshness-scanner")


async def stop_freshness_scanner(task: asyncio.Task) -> None:
    if task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("freshness scanner: error during shutdown")

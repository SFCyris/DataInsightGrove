"""Async job manager — runs pipeline executions in the background.

Persists state transitions to the `runs` SQLite table and pushes events to the
TopicHub on `run:<run_id>`. Single-process, in-memory task tracking.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.engine.executor import execute
from dig.engine.pipeline import Pipeline
from dig.jobs.hub import hub
from dig.jobs.webhooks import dispatch as dispatch_webhooks
from dig.storage.db import SessionLocal
from dig.storage.models import Run

log = logging.getLogger(__name__)

# Reference to the API process's main event loop. Captured on first submit()
# and consumed by worker threads (the executor's subpipeline lookup,
# webhook_trigger step) that need to dispatch coroutines back to the main
# loop. `asyncio.get_event_loop()` from a worker thread is deprecated since
# 3.10 and raises in 3.12+; opening a new loop with `asyncio.run()` strands
# the aiosqlite engine on the wrong loop. This module-level reference is
# the single source of truth.
_main_loop: asyncio.AbstractEventLoop | None = None


def main_loop() -> asyncio.AbstractEventLoop | None:
    """Return the API main event loop, or None if no submit has run yet."""
    return _main_loop


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    async def submit(self, pipeline: Pipeline, *, sample_rows: int | None = None) -> str:
        """Insert the Run row synchronously, then kick off the background task.

        Returning before the row exists would race with API consumers who
        immediately poll /runs/{id}.
        """
        global _main_loop
        if _main_loop is None:
            _main_loop = asyncio.get_running_loop()
        run_id = str(ULID())
        async with SessionLocal() as session:
            row = Run(id=run_id, pipeline_id=pipeline.id, status="queued")
            session.add(row)
            await session.commit()
        task = asyncio.create_task(self._run(run_id, pipeline, sample_rows))
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return run_id

    async def _run(self, run_id: str, pipeline: Pipeline, sample_rows: int | None) -> None:
        await hub.publish(f"run:{run_id}", {"status": "queued"})

        started_at = _utcnow()
        try:
            await self._set_status(run_id, "running", started_at=started_at, progress=0.05)
            await hub.publish(f"run:{run_id}", {"status": "running", "progress": 0.05, "stage": "compiling"})

            # The executor is synchronous-ish (releases the GIL inside DuckDB);
            # run it in a thread so the event loop stays responsive.
            result = await asyncio.to_thread(execute, pipeline, run_id=run_id, sample_rows=sample_rows)

            finished_at = _utcnow()
            # Phase-A-pro #7: emit data.quality.violation events for any
            # check_data step that found violations. We walk the run's
            # validation artifacts (already attached above by the
            # executor's validation pass) and emit one event per
            # violating check. The notification rule engine handles
            # routing to in-app / email / webhook.
            await self._emit_check_violations(pipeline, run_id, result.artifacts)
            # Phase-A-pro #7 follow-up: profile drift + row-count
            # anomaly detection runs against this run's metrics + the
            # last N succeeded runs from the DB. Emits
            # `data.profile.drift` and `data.row_count.anomaly` events.
            await self._emit_drift_events(
                pipeline=pipeline, run_id=run_id, node_metrics=result.nodeMetrics or {},
            )
            await self._set_status(
                run_id,
                "succeeded",
                finished_at=finished_at,
                progress=1.0,
                output_paths=list(result.outputs.values()),
                artifacts=result.artifacts or None,
                node_metrics=result.nodeMetrics or None,
                nan_origins=result.nanOrigins or None,
            )
            await hub.publish(f"run:{run_id}", {
                "status": "succeeded",
                "progress": 1.0,
                "outputs": result.outputs,
                "rowCounts": result.rowCounts,
                "elapsedMs": result.elapsedMs,
                "artifacts": result.artifacts,
                "nodeMetrics": result.nodeMetrics,
                "nanOrigins": result.nanOrigins,
            })
            await self._fire_webhooks(pipeline, {
                "runId": run_id,
                "pipelineId": pipeline.id,
                "pipelineName": pipeline.name,
                "status": "succeeded",
                "startedAt": started_at.isoformat(),
                "finishedAt": finished_at.isoformat(),
                "elapsedMs": result.elapsedMs,
                "outputs": result.outputs,
                "rowCounts": result.rowCounts,
                "artifacts": result.artifacts,
            })
        except Exception as e:
            # Log the full traceback server-side (operators need it for
            # debugging) but ONLY the type + message goes into the Run row.
            # The Run row is exposed by ``GET /runs/{id}`` to any
            # authenticated caller, and the full traceback leaks the
            # deployment's filesystem paths (``/Volumes/.../backend/dig/...``,
            # the operator's home directory, the Python interpreter path,
            # internal module names + line numbers — all useful to an
            # attacker fingerprinting the host or crafting path-based
            # exploits). Multi-user / enterprise deployments need this
            # gate; single-user self-host setups are unaffected because
            # the operator has shell access and reads ``log.exception``
            # output directly.
            log.exception("run %s failed", run_id)
            finished_at = _utcnow()
            await self._set_status(
                run_id,
                "failed",
                finished_at=finished_at,
                error=f"{type(e).__name__}: {e}",
            )
            await hub.publish(f"run:{run_id}", {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            })
            # Emit a run.failed event. Notification rules pick it up and
            # decide whether to create an in-app notification (and, in the
            # future, dispatch to email / Slack / webhook).
            from dig.api.events import EventKinds, emit_event
            await emit_event(
                EventKinds.RUN_FAILED,
                run_id=run_id,
                pipeline_id=pipeline.id,
                pipeline_name=pipeline.name,
                error=str(e),
                error_type=type(e).__name__,
            )
            await self._fire_webhooks(pipeline, {
                "runId": run_id,
                "pipelineId": pipeline.id,
                "pipelineName": pipeline.name,
                "status": "failed",
                "startedAt": started_at.isoformat(),
                "finishedAt": finished_at.isoformat(),
                "error": f"{type(e).__name__}: {e}",
            })

    async def _emit_check_violations(
        self,
        pipeline: Pipeline,
        run_id: str,
        artifacts: dict[str, list[dict[str, Any]]] | None,
    ) -> None:
        """Walk the run's validation artifacts and emit a
        `data.quality.violation` event for every check_data step that
        found violations. Best-effort — never fails the run."""
        if not artifacts:
            return
        try:
            from dig.api.events import emit_event
            for key, arts in artifacts.items():
                if not key.startswith("_validation:"):
                    continue
                for art in arts:
                    if (art.get("step_id") != "check_data"):
                        continue
                    metrics = art.get("metrics") or {}
                    violations = metrics.get("violations") or 0
                    if violations <= 0:
                        continue
                    sev = str(metrics.get("severity") or "warn")
                    level = "error" if sev == "error" else "warning"
                    await emit_event(
                        "data.quality.violation",
                        run_id=run_id,
                        pipeline_id=pipeline.id,
                        pipeline_name=pipeline.name,
                        node_id=art.get("node_id"),
                        check_kind=metrics.get("check_kind"),
                        check_name=metrics.get("check_name") or art.get("node_id"),
                        violations=violations,
                        total=metrics.get("total"),
                        first_bad=metrics.get("first_bad"),
                        severity=sev,
                        level=level,
                    )
        except Exception:
            log.exception("data-quality event emission failed for run %s", run_id)

    async def _emit_drift_events(
        self,
        *,
        pipeline: Pipeline,
        run_id: str,
        node_metrics: dict[str, dict[str, Any]],
    ) -> None:
        """Run profile drift + row-count anomaly detection against the
        last N succeeded runs and emit any detected events. Best-
        effort — never fails the run."""
        if not node_metrics:
            return
        try:
            from dig.api.events import emit_event
            from dig.engine.dq_drift import detect_drift_events
            from dig.storage.db import SessionLocal
            async with SessionLocal() as session:
                events = await detect_drift_events(
                    pipeline_id=pipeline.id,
                    pipeline_name=pipeline.name,
                    current_run_id=run_id,
                    current_node_metrics=node_metrics,
                    session=session,
                )
            for ev in events:
                kind = ev.pop("kind")
                # `level` is part of the event context the rule engine
                # may template into the notification's level field.
                await emit_event(kind, run_id=run_id, **ev)
        except Exception:
            log.exception("drift detection failed for run %s", run_id)

    async def _fire_webhooks(self, pipeline: Pipeline, payload: dict[str, Any]) -> None:
        """Best-effort webhook dispatch — never propagates failures.

        Fires both per-pipeline webhooks (from pipeline.webhooks) AND any
        global webhooks (rows in the global_webhooks table). The two sets
        merge into one Pipeline-shaped object so dispatch_webhooks treats
        them identically — it doesn't care where the webhook list came from.

        Webhook delivery is fire-and-forget from the run's perspective: a
        slow / broken receiver must not block the run from being marked
        terminal in the DB or hide its status from the UI. The dispatch
        helper has its own retry + timeout; here we just shield against
        any leak that escapes.
        """
        try:
            from dig.api.settings import load_enabled_global_webhooks
            from dig.engine.pipeline import Webhook
            global_hooks = await load_enabled_global_webhooks()
            combined_hooks = list(pipeline.webhooks) + [Webhook(**g) for g in global_hooks]
            if not combined_hooks:
                return
            # Build a thin shim so dispatch_webhooks sees a Pipeline-shaped
            # object — we don't mutate the real pipeline (could affect future
            # use elsewhere in this run's lifecycle).
            shim = pipeline.model_copy(update={"webhooks": combined_hooks})
            await dispatch_webhooks(shim, payload)
        except Exception:  # noqa: BLE001
            log.exception("webhook dispatch failed for run %s", payload.get("runId"))

    async def _set_status(self, run_id: str, status: str, **fields: Any) -> None:
        async with SessionLocal() as session:
            row = await session.get(Run, run_id)
            if row is None:
                return
            row.status = status
            for k, v in fields.items():
                setattr(row, k, v)
            await session.commit()

    async def shutdown(self) -> None:
        """Cancel all in-flight runs and mark them aborted.

        Called from the FastAPI lifespan on shutdown. Without this, SIGTERM /
        uvicorn reload leaves rows stuck at `running` forever.
        """
        if not self._tasks:
            return
        # Snapshot id → task pairs BEFORE cancelling. The done-callback
        # (_run() registers one) removes entries from self._tasks as tasks
        # finish, so we can't iterate self._tasks across the gather.
        snapshot = list(self._tasks.items())
        for _, task in snapshot:
            task.cancel()
        await asyncio.gather(*(t for _, t in snapshot), return_exceptions=True)

        # Mark each genuinely-cancelled task as aborted. Skip tasks that
        # finished cleanly between submit and shutdown — without this guard,
        # we'd overwrite a successful run's status with "failed: aborted".
        for rid, task in snapshot:
            if not task.cancelled():
                # Task finished on its own (success or already-failed) before
                # we could cancel it. The _run() body already wrote the final
                # status; don't clobber it.
                continue
            try:
                await self._set_status(
                    rid, "failed",
                    finished_at=_utcnow(),
                    error="aborted: backend shut down before run completed",
                )
                await hub.publish(f"run:{rid}", {
                    "status": "failed", "error": "aborted: backend shutdown",
                })
            except Exception:
                log.exception("could not mark run %s as aborted", rid)


jobs = JobManager()

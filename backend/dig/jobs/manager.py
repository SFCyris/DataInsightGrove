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


# Pen-tester round-3: storing `f"{type(e).__name__}: {e}"` directly leaked
# the full Pydantic ``ValidationError`` body — which includes the user's
# raw ``input_value`` for every failing field — into a Run row that any
# authenticated caller can fetch via ``GET /runs/{id}``. For a pipeline
# whose input was a 5 MB JSON document, that's a 5 MB error payload; for
# a doc that contained file URIs / API keys / SQL fragments, that's
# unbounded leakage.
#
# Cap the human-readable error to a single line + 500 chars; full traceback
# stays in ``log.exception`` server-side where the operator can read it.
_ERROR_DISPLAY_CAP = 500


def _safe_error_message(exc: BaseException) -> str:
    """Format an exception for the Run.error column / events / webhooks.

    Single line, length-capped, no traceback. The full context is
    available in the server log via ``log.exception``.
    """
    try:
        msg = str(exc)
    except Exception:  # noqa: BLE001
        msg = "<unrenderable>"
    # Collapse multi-line errors (e.g. Pydantic ValidationError) to one
    # line so the column doesn't carry attacker-controlled newlines.
    msg = msg.replace("\r", " ").replace("\n", " ").strip()
    if len(msg) > _ERROR_DISPLAY_CAP:
        msg = msg[: _ERROR_DISPLAY_CAP - 3] + "..."
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


class JobManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        # Round-4 QA finding: ``shutdown()`` snapshots the in-flight task
        # set once. A ``submit()`` arriving mid-cancel (e.g. a webhook
        # round-trip racing the SIGTERM handler) would happily add a
        # fresh task AFTER the snapshot, which then leaks past the API
        # process exit with its Run row stuck at ``queued``. Gate every
        # submission on this flag once shutdown begins.
        self._shutting_down = False

    async def submit(self, pipeline: Pipeline, *, sample_rows: int | None = None) -> str:
        """Insert the Run row synchronously, then kick off the background task.

        Returning before the row exists would race with API consumers who
        immediately poll /runs/{id}.
        """
        if self._shutting_down:
            # 503 maps to "service unavailable" — the right shape for
            # "we're shutting down, retry later".
            from fastapi import HTTPException
            raise HTTPException(503, "DIG is shutting down; refusing new runs")
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
        # Inflight gauge — bumped on running, decremented in finally.
        from dig.observability import inc, set_gauge
        # NB: this is racy for the gauge value across coroutines but the
        # counter monotonic-add is correct; for our throughput (a few
        # runs per second peak) the gauge is good enough as a "ballpark".
        try:
            set_gauge("dig_inflight_runs", float(len(self._tasks)))
        except Exception:
            pass

        await hub.publish(f"run:{run_id}", {"status": "queued"})

        started_at = _utcnow()
        try:
            await self._set_status(run_id, "running", started_at=started_at, progress=0.05)
            await hub.publish(f"run:{run_id}", {"status": "running", "progress": 0.05, "stage": "compiling"})

            # The executor is synchronous-ish (releases the GIL inside DuckDB);
            # run it in a thread so the event loop stays responsive.
            result = await asyncio.to_thread(execute, pipeline, run_id=run_id, sample_rows=sample_rows)

            finished_at = _utcnow()
            # Emit data.quality.violation events for any
            # check_data step that found violations. We walk the run's
            # validation artifacts (already attached above by the
            # executor's validation pass) and emit one event per
            # violating check. The notification rule engine handles
            # routing to in-app / email / webhook.
            await self._emit_check_violations(pipeline, run_id, result.artifacts)
            # Profile drift + row-count
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
            try:
                inc("dig_runs_total", labels={"status": "succeeded"})
            except Exception:
                pass
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
        except asyncio.CancelledError:
            # Round-5 W4: a user-triggered cancel arrives as a
            # ``CancelledError`` (``task.cancel()``). Mark the row
            # ``cancelled`` so the UI and webhooks see a distinct
            # terminal state separate from a real exception. Reraise
            # afterwards so the cancellation propagates correctly to
            # the supervising loop on shutdown.
            log.info("run %s cancelled by user", run_id)
            finished_at = _utcnow()
            await self._set_status(
                run_id,
                "cancelled",
                finished_at=finished_at,
                error="cancelled by user",
            )
            try:
                inc("dig_runs_total", labels={"status": "cancelled"})
            except Exception:
                pass
            await hub.publish(f"run:{run_id}", {
                "status": "cancelled",
                "progress": None,
                "error": "cancelled by user",
            })
            # Round-8: fire webhooks + emit run.cancelled so notification
            # rules can match cancellations the same way they match
            # failures. Without this, cancelled runs were silent to any
            # external integration.
            from dig.api.events import EventKinds, emit_event
            await emit_event(
                EventKinds.RUN_CANCELLED,
                run_id=run_id,
                pipeline_id=pipeline.id,
                pipeline_name=pipeline.name,
            )
            await self._fire_webhooks(pipeline, {
                "runId": run_id,
                "pipelineId": pipeline.id,
                "pipelineName": pipeline.name,
                "status": "cancelled",
                "startedAt": started_at.isoformat(),
                "finishedAt": finished_at.isoformat(),
                "error": "cancelled by user",
            })
            raise
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
            err_display = _safe_error_message(e)
            await self._set_status(
                run_id,
                "failed",
                finished_at=finished_at,
                error=err_display,
            )
            try:
                inc("dig_runs_total", labels={"status": "failed"})
            except Exception:
                pass
            await hub.publish(f"run:{run_id}", {
                "status": "failed",
                "error": err_display,
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
                error=err_display,
                error_type=type(e).__name__,
            )
            await self._fire_webhooks(pipeline, {
                "runId": run_id,
                "pipelineId": pipeline.id,
                "pipelineName": pipeline.name,
                "status": "failed",
                "startedAt": started_at.isoformat(),
                "finishedAt": finished_at.isoformat(),
                "error": err_display,
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
        """Atomically update a Run row's status + extra fields.

        Round-8 fix: previously this was a read-modify-write
        (``session.get`` → mutate → commit). Two concurrent writers
        (e.g. the user-cancel endpoint + the task's own except branch)
        could read the same starting row and silently clobber each
        other on commit. We now issue a single UPDATE with a
        ``status NOT IN (terminal states)`` predicate so only the
        FIRST writer to a still-running row wins; subsequent writers
        no-op (matched zero rows).
        """
        from sqlalchemy import update as _sa_update
        _TERMINAL = ("succeeded", "failed", "cancelled")
        async with SessionLocal() as session:
            # Allow shutdown-aborted transitions only on still-running rows.
            # When the new status is itself terminal we use the predicate;
            # for non-terminal updates (rare — e.g. progress?) we skip it.
            stmt = (
                _sa_update(Run)
                .where(Run.id == run_id)
                .where(Run.status.notin_(_TERMINAL))
                .values(status=status, **fields)
            )
            res = await session.execute(stmt)
            await session.commit()
            if res.rowcount == 0:
                # Either the row vanished or another writer already
                # landed a terminal status. Log + bail; the caller
                # treats this as a successful set.
                log.debug(
                    "run %s already in a terminal state; skipped status=%s",
                    run_id, status,
                )

    async def shutdown(self) -> None:
        """Cancel all in-flight runs and mark them aborted.

        Called from the FastAPI lifespan on shutdown. Without this, SIGTERM /
        uvicorn reload leaves rows stuck at `running` forever.
        """
        # Set the gate FIRST so new submissions can't slip in past the
        # snapshot we take below (round-4 QA finding).
        self._shutting_down = True
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
        # Round-8: also skip rows whose status is already a terminal value
        # (succeeded / failed / cancelled). The task's own except-branch may
        # have written "cancelled" before we got here when the user-cancel
        # endpoint and shutdown raced — without this check we'd overwrite a
        # legitimate "cancelled" with "failed: aborted".
        for rid, task in snapshot:
            if not task.cancelled():
                continue
            try:
                async with SessionLocal() as session:
                    row = await session.get(Run, rid)
                    if row is None or row.status in ("succeeded", "failed", "cancelled"):
                        continue
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

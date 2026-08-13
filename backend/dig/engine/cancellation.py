"""Cooperative cancellation for pipeline runs.

``JobManager`` dispatches a run with ``asyncio.to_thread(execute, …)`` and
cancels it with ``task.cancel()``. That cancels the *awaiting coroutine* — it
cannot interrupt the worker thread, because Python threads have no preemptive
kill. So the UI flipped to "cancelled" while the run kept going: CPU stayed
pegged, and — worse — the executor's sink writes still landed *after* the run
had been reported cancelled.

The fix is cooperative: the API records a cancellation request here, and the
executor checks between units of work (each pre-materialised Polars node, each
output) and raises. Checks sit at boundaries, never mid-query, so a cancelled
run stops at a consistent point rather than half-written.

Deliberately dependency-free so both ``dig.engine`` and ``dig.jobs`` can import
it without a cycle.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_requested: set[str] = set()


class RunCancelled(Exception):
    """Raised inside the executor when a cancellation has been requested."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"run {run_id} cancelled")
        self.run_id = run_id


def request_cancel(run_id: str) -> None:
    """Ask the run to stop at its next checkpoint. Idempotent."""
    with _lock:
        _requested.add(run_id)


def is_cancelled(run_id: str) -> bool:
    with _lock:
        return run_id in _requested


def clear(run_id: str) -> None:
    """Drop the flag once a run reaches a terminal state.

    Without this the set would grow for the process lifetime, and a recycled
    run id could inherit a stale cancellation.
    """
    with _lock:
        _requested.discard(run_id)


def raise_if_cancelled(run_id: str) -> None:
    """Checkpoint helper — call between units of work."""
    if is_cancelled(run_id):
        raise RunCancelled(run_id)

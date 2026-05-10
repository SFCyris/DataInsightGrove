"""Profile drift + row-count anomaly detectors.

Phase-A-pro #7 follow-up: now that the `check_data` step ships,
DIG also detects two implicit data-quality signals automatically
(no user configuration required):

1. **Profile drift** — when a pipeline node's output schema changes
   between two consecutive succeeded runs (column added / removed,
   in the simplest first version). Emits `data.profile.drift`.

2. **Row-count anomaly** — when the current run's `rows_out` for a
   node deviates more than ±2σ from the historical mean of the last
   N succeeded runs. Emits `data.row_count.anomaly`.

Both detectors run inside `JobManager._emit_drift_events` after a run
succeeds, alongside the existing `_emit_check_violations` call. Same
delivery path: events go through the rule engine and surface as in-app
notifications.

Patent posture (see `docs/PRIOR_ART_MAP.md` § 11):
  - We use ONLY classical statistics — z-score against historical
    mean / stddev. No ML. Z-scores are textbook content (1900s-era).
  - Schema-diff is a simple set comparison, prior art back to GNU
    `diff` (1974).
  - The free-tier individual scope explicitly avoids replicating
    Monte Carlo / Datadog / Bigeye / Anomalo proprietary mechanisms
    (autothreshold ML, statistical-band fitting, root-cause inference).
"""
from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dig.storage.models import Run

log = logging.getLogger(__name__)


# Tunable thresholds. Defaults are conservative: a user editing a
# pipeline expects schema changes (don't spam them), but a column
# silently disappearing in a SCHEDULED run is a real signal.
ROW_COUNT_HISTORY_WINDOW = 5     # last N succeeded runs to compute baseline
ROW_COUNT_Z_THRESHOLD = 2.0      # |z| ≥ this → anomaly
ROW_COUNT_MIN_HISTORY = 3        # need ≥ this many runs to trust the baseline
ROW_COUNT_MIN_DEVIATION_PCT = 10  # ignore deviations <10% even if z is high (noise floor)


async def detect_drift_events(
    pipeline_id: str,
    pipeline_name: str,
    current_run_id: str,
    current_node_metrics: dict[str, dict[str, Any]],
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Returns a list of event dicts to emit, given the current run's
    metrics. Caller is responsible for actually emitting them via
    `dig.api.events.emit_event`. Splitting compute from emit makes
    this function easy to unit-test."""
    events: list[dict[str, Any]] = []

    # Fetch up to N+1 most recent succeeded runs for this pipeline,
    # most recent first. The current run is excluded — we only want
    # PRIOR succeeded runs as the baseline.
    res = await session.execute(
        select(Run)
        .where(Run.pipeline_id == pipeline_id)
        .where(Run.status == "succeeded")
        .where(Run.id != current_run_id)
        .order_by(Run.finished_at.desc())
        .limit(ROW_COUNT_HISTORY_WINDOW)
    )
    history = list(res.scalars().all())
    if not history:
        # First-ever run for this pipeline — nothing to compare against.
        return events

    prior = history[0]
    prior_metrics = prior.node_metrics or {}

    # Schema drift — compare current vs immediately-prior run.
    events.extend(_detect_schema_drift(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline_name,
        current=current_node_metrics,
        prior=prior_metrics,
        prior_run_id=prior.id,
    ))

    # Row-count anomaly — z-score against the last N runs.
    events.extend(_detect_row_count_anomaly(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline_name,
        current=current_node_metrics,
        history=history,
    ))

    return events


# ---- Schema drift -------------------------------------------------------


def _detect_schema_drift(
    *,
    pipeline_id: str,
    pipeline_name: str,
    current: dict[str, dict[str, Any]],
    prior: dict[str, dict[str, Any]],
    prior_run_id: str,
) -> list[dict[str, Any]]:
    """For each node present in BOTH runs, diff the column lists. We
    intentionally don't emit events for nodes that only exist in one
    run — that's a pipeline-edit signal, not a data-drift signal."""
    out: list[dict[str, Any]] = []
    for node_id, cur in current.items():
        cur_cols = cur.get("columns")
        prv = prior.get(node_id)
        if not isinstance(cur_cols, list) or not prv:
            continue
        prv_cols = prv.get("columns")
        if not isinstance(prv_cols, list):
            continue

        cur_set = set(cur_cols)
        prv_set = set(prv_cols)
        added = sorted(cur_set - prv_set)
        removed = sorted(prv_set - cur_set)
        if not added and not removed:
            continue

        out.append({
            "kind": "data.profile.drift",
            "pipeline_id": pipeline_id,
            "pipeline_name": pipeline_name,
            "node_id": node_id,
            "level": "warning",
            "added": added,
            "removed": removed,
            "added_count": len(added),
            "removed_count": len(removed),
            "prior_run_id": prior_run_id,
            "summary": _summarise_drift(added, removed),
        })
    return out


def _summarise_drift(added: list[str], removed: list[str]) -> str:
    """Human-readable one-liner for the notification template. Keep
    short so it fits in the notifications panel without truncation."""
    parts: list[str] = []
    if added:
        sample = ", ".join(added[:3])
        if len(added) > 3:
            sample += f", +{len(added) - 3} more"
        parts.append(f"added [{sample}]")
    if removed:
        sample = ", ".join(removed[:3])
        if len(removed) > 3:
            sample += f", +{len(removed) - 3} more"
        parts.append(f"removed [{sample}]")
    return " · ".join(parts) if parts else "no change"


# ---- Row-count anomaly --------------------------------------------------


def _detect_row_count_anomaly(
    *,
    pipeline_id: str,
    pipeline_name: str,
    current: dict[str, dict[str, Any]],
    history: list[Run],
) -> list[dict[str, Any]]:
    """Z-score against the history window. Emit when |z| ≥
    ROW_COUNT_Z_THRESHOLD AND the absolute % deviation is large enough
    to matter (filters out tiny variance on small-row pipelines)."""
    out: list[dict[str, Any]] = []
    for node_id, cur in current.items():
        cur_rows = cur.get("rows_out")
        if not isinstance(cur_rows, (int, float)):
            continue

        # Gather historical row counts for this node.
        historical: list[float] = []
        for r in history:
            metrics = r.node_metrics or {}
            v = (metrics.get(node_id) or {}).get("rows_out")
            if isinstance(v, (int, float)):
                historical.append(float(v))
        if len(historical) < ROW_COUNT_MIN_HISTORY:
            continue

        mean = sum(historical) / len(historical)
        var = sum((v - mean) ** 2 for v in historical) / len(historical)
        stddev = math.sqrt(var)
        if stddev == 0:
            # Constant history — only flag as anomaly if the current
            # value is substantially different in absolute terms.
            if mean == 0 or cur_rows == mean:
                continue
            pct_dev = abs(cur_rows - mean) / max(mean, 1) * 100
            if pct_dev < ROW_COUNT_MIN_DEVIATION_PCT:
                continue
            z = float("inf") if cur_rows > mean else float("-inf")
        else:
            z = (cur_rows - mean) / stddev
            pct_dev = abs(cur_rows - mean) / max(mean, 1) * 100
            if abs(z) < ROW_COUNT_Z_THRESHOLD:
                continue
            if pct_dev < ROW_COUNT_MIN_DEVIATION_PCT:
                continue

        out.append({
            "kind": "data.row_count.anomaly",
            "pipeline_id": pipeline_id,
            "pipeline_name": pipeline_name,
            "node_id": node_id,
            "level": "warning",
            "current": int(cur_rows),
            "mean": round(mean, 1),
            "stddev": round(stddev, 1),
            "z_score": _round_z(z),
            "pct_deviation": round(pct_dev, 1),
            "direction": "up" if cur_rows > mean else "down",
            "history_window": len(historical),
            "summary": _summarise_anomaly(cur_rows, mean, pct_dev),
        })
    return out


def _round_z(z: float) -> float:
    if z == float("inf"):
        return 999.0
    if z == float("-inf"):
        return -999.0
    return round(z, 2)


def _summarise_anomaly(current: float, mean: float, pct: float) -> str:
    arrow = "▲" if current > mean else "▼"
    return f"{arrow} {pct:.0f}% vs avg ({int(mean):,} → {int(current):,} rows)"

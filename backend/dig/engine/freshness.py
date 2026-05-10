"""Freshness computation — Phase A Layer 2.

Pure functions: parse human duration strings, compute per-node freshness
state from the declared SLA + the latest run timestamp. The scheduler
that *acts on* these values (running pipelines whose freshness expired)
lands in Phase B. This module is consumed by the
`GET /pipelines/{id}/freshness` endpoint to drive the canvas halo.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Literal

FreshnessState = Literal["fresh", "due", "stale", "never"]

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhdwSMHDW])\s*$")
_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86_400,
    "w": 86_400 * 7,
}


def parse_duration(value: str) -> timedelta:
    """Parse a short human duration like "30m", "2h", "1d", "7w".

    Raises ValueError on malformed input. Caller (the API endpoint) catches
    + downgrades to a never-fresh state so a typo in the SLA doesn't 500
    the whole canvas.
    """
    m = _DURATION_RE.match(value)
    if not m:
        raise ValueError(
            f"freshness duration {value!r} is not in '<int><unit>' form "
            f"(e.g. '30m', '2h', '1d', '7w')"
        )
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit not in _UNIT_SECONDS:
        raise ValueError(f"unknown duration unit {unit!r}")
    return timedelta(seconds=n * _UNIT_SECONDS[unit])


def compute_node_freshness(
    sla: str,
    warn_at: str | None,
    last_run_at: datetime | None,
    now: datetime | None = None,
) -> FreshnessState:
    """Map (sla, warn_at, last_run_at) -> {fresh, due, stale, never}.

    - never: no run has produced this node's output yet.
    - stale: now - last_run_at > sla.
    - due:   warn_at is set AND now - last_run_at > (sla - warn_at).
    - fresh: otherwise.

    `warn_at` is interpreted as "halo flips amber within this window of
    becoming stale" — e.g. sla=24h, warn_at=4h means the halo is amber
    when the data is 20h+ old (within 4h of the 24h SLA).

    Caller passes `now` for testability; defaults to `datetime.now(UTC)`.
    """
    if last_run_at is None:
        return "never"

    now = now or datetime.now(timezone.utc)
    # last_run_at may be naive in some code paths; assume UTC if so.
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)

    age = now - last_run_at
    sla_td = parse_duration(sla)

    if age > sla_td:
        return "stale"

    if warn_at:
        warn_window = parse_duration(warn_at)
        # The "due" zone is the last `warn_window` of the SLA window.
        due_threshold = sla_td - warn_window
        if age > due_threshold:
            return "due"

    return "fresh"

"""Event vocabulary + emit_event() — the rule-engine entrypoint.

Events are ALWAYS emitted by producers. Whether a notification (or, in
the future, an email / Slack message / webhook) is created from an event
is decided by NotificationRules — user-configurable matchers that fire
on specific event kinds with optional filters, render templates, and
call `record_notification()`.

Design notes:

  - Producers call `emit_event(kind, **context)` and move on. Failures
    in the rule engine never propagate back to the producer (logged but
    swallowed) — same contract as `record_notification()`.

  - Event kinds are dot-namespaced strings. The rule matcher accepts
    exact ("run.failed") and wildcard ("run.*", "freshness.*", "*")
    patterns. Wildcards are simple prefix matches; no regex.

  - We do NOT persist events themselves yet. Rules consume the events
    in-process; only the resulting notifications are stored. A
    persisted event log (for replay / debugging / audit) is a Phase B
    concern when the freshness scheduler lands.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Final

log = logging.getLogger(__name__)


# ---- Event vocabulary --------------------------------------------------
#
# All event kinds the producers may emit. Constants exist so that typos
# fail at import time, not silently at runtime. The rule UI's event
# picker enumerates this list. Adding a new kind is one line here +
# documentation in the rules form's help text.

class EventKinds:
    # Pipeline run lifecycle
    RUN_QUEUED      : Final = "run.queued"
    RUN_STARTED     : Final = "run.started"
    RUN_SUCCEEDED   : Final = "run.succeeded"
    RUN_FAILED      : Final = "run.failed"
    RUN_SLOW        : Final = "run.slow"        # took longer than its baseline

    # Freshness — TRANSITIONS, not steady states. fresh→due means "this
    # asset just crossed from green to yellow"; rules typically want to
    # alert on the transition, not every poll while it stays yellow.
    FRESHNESS_DUE       : Final = "freshness.due"        # entered the warning window
    FRESHNESS_STALE     : Final = "freshness.stale"      # passed the SLA
    FRESHNESS_RECOVERED : Final = "freshness.recovered"  # was due/stale, now fresh again

    # System
    SYSTEM_STARTUP  : Final = "system.startup"
    SYSTEM_SHUTDOWN : Final = "system.shutdown"
    SYSTEM_ERROR    : Final = "system.error"

    # Auth (Phase B+ once auth is wired)
    LOGIN_SUCCESS : Final = "auth.login_success"
    LOGIN_FAILED  : Final = "auth.login_failed"

    # Resource pressure
    DISK_LOW    : Final = "resources.disk_low"
    MEMORY_HIGH : Final = "resources.memory_high"

    # Data quality (Phase-A-pro #7) — emitted by the check_data step
    # when its assertion finds violating rows. Severity carried in the
    # event context determines whether downstream rules fire as a
    # warning or an error.
    DATA_QUALITY_VIOLATION : Final = "data.quality.violation"
    DATA_PROFILE_DRIFT     : Final = "data.profile.drift"
    DATA_ROW_COUNT_ANOMALY : Final = "data.row_count.anomaly"


# Flat list for UI dropdowns + validation. Keep in sync with EventKinds.
ALL_EVENT_KINDS: tuple[str, ...] = (
    EventKinds.RUN_QUEUED, EventKinds.RUN_STARTED, EventKinds.RUN_SUCCEEDED,
    EventKinds.RUN_FAILED, EventKinds.RUN_SLOW,
    EventKinds.FRESHNESS_DUE, EventKinds.FRESHNESS_STALE, EventKinds.FRESHNESS_RECOVERED,
    EventKinds.SYSTEM_STARTUP, EventKinds.SYSTEM_SHUTDOWN, EventKinds.SYSTEM_ERROR,
    EventKinds.LOGIN_SUCCESS, EventKinds.LOGIN_FAILED,
    EventKinds.DISK_LOW, EventKinds.MEMORY_HIGH,
    EventKinds.DATA_QUALITY_VIOLATION, EventKinds.DATA_PROFILE_DRIFT,
    EventKinds.DATA_ROW_COUNT_ANOMALY,
)


# ---- Event-kind matching -----------------------------------------------


def event_kind_matches(rule_pattern: str, event_kind: str) -> bool:
    """Does `event_kind` match `rule_pattern`?

    Patterns:
      - "*"             matches anything
      - "run.*"         matches run.queued, run.failed, etc.
      - "run.failed"    exact
    """
    if rule_pattern == "*":
        return True
    if rule_pattern == event_kind:
        return True
    if rule_pattern.endswith(".*"):
        prefix = rule_pattern[:-1]   # keep the dot
        return event_kind.startswith(prefix)
    return False


# ---- emit_event --------------------------------------------------------


async def emit_event(kind: str, **context: Any) -> None:
    """Producer entrypoint. Always succeeds (logs + swallows on error).

    Looks up enabled NotificationRules whose `event_kind` matches,
    evaluates each rule's filters against the context, respects the
    rule's cooldown, renders the rule's title/message templates, and
    calls `record_notification()` for each fire.

    Context conventions (used by templates + filters):
      - `pipeline_id`, `pipeline_name`
      - `run_id`
      - `node_id`, `node_label`
      - `group_id`, `group_label`
      - `column` (for column-level events, future)
      - `error`, `error_type` (for failures)
      - `last_run_at` (for freshness)
      - any extra fields the producer wants to attach
    """
    # Always stamp an emitted-at timestamp so templates can reference it
    # without callers having to pass it.
    context.setdefault("emitted_at", datetime.now(timezone.utc).isoformat())

    # Imported lazily to avoid circular imports — rules.py imports
    # records, records imports... etc.
    try:
        from dig.api.notification_rules import apply_rules_for_event
        await apply_rules_for_event(kind, context)
    except Exception:
        log.exception("rule engine failed for event %s ctx=%r", kind, context)

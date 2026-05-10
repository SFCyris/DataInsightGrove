"""Notification rules — match events, apply filters, render templates,
fire notifications.

Architecture:
  events.py emits events (`emit_event`)
       │
       ▼
  apply_rules_for_event(kind, context)
       │  loads enabled rules where event_kind matches
       │  evaluates filters (pipeline_id, group_id, node_id, …)
       │  checks cooldown
       │  renders title/message templates
       ▼
  record_notification()  →  Notifications table
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import re as _re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.api.events import ALL_EVENT_KINDS, EventKinds, event_kind_matches
from dig.api.notifications import record_notification
from dig.storage.db import SessionLocal, get_session
from dig.storage.models import NotificationRule

log = logging.getLogger(__name__)

router = APIRouter(prefix="/notification-rules", tags=["notification-rules"])


# ---- Schemas ------------------------------------------------------------


class RuleAction(BaseModel):
    """Action to take when a rule fires. Today only `in_app`; future
    expansion to email / slack / webhook keeps the schema stable by
    adding `channel` variants here."""
    level: str = "auto"     # "notification" | "warning" | "error" | "auto"
    title: str              # template (e.g. "{pipeline_name} run failed")
    message: str | None = None
    channel: str = "in_app"  # "in_app" today; "email" / "slack" later


class RuleIn(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    event_kind: str
    filters: dict[str, Any] | None = None
    action: RuleAction
    cooldown_seconds: int | None = None


class RuleOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    enabled: bool
    event_kind: str
    filters: dict[str, Any] | None = None
    action: RuleAction
    cooldown_seconds: int | None = None
    last_fired_at: datetime | None = None
    fire_count: int
    is_builtin: bool
    created_at: datetime
    updated_at: datetime


def _to_out(r: NotificationRule) -> RuleOut:
    return RuleOut(
        id=r.id,
        name=r.name,
        description=r.description,
        enabled=r.enabled,
        event_kind=r.event_kind,
        filters=r.filters,
        action=RuleAction(**r.action),
        cooldown_seconds=r.cooldown_seconds,
        last_fired_at=r.last_fired_at,
        fire_count=r.fire_count,
        is_builtin=r.is_builtin,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


# ---- Template rendering ------------------------------------------------


_PLACEHOLDER_RE = _re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render(template: str, context: dict[str, Any]) -> str:
    """Render a notification template with simple {placeholder} substitution.

    Round-3 pen-tester finding PEN #1: the previous implementation used
    Python's ``str.format`` via a custom ``Formatter`` subclass. That
    accepts attribute access (``{pipeline.__class__.__init__.__globals__}``),
    indexing (``{pipeline[secret]}``), conversion specs (``{x!r}``), and
    format specs (``{x:>1000000}`` → mass memory). All are
    SSTI / format-string-injection vectors. Rule templates are
    user-authored, so the user IS the attacker in this threat model
    (auth-required code execution / info leak).

    We replace it with a strict regex substitution: only bare
    ``{name}`` patterns where ``name`` matches an identifier. Everything
    else (``{x.y}``, ``{x[y]}``, ``{x!r}``, ``{x:0>10}``) is left as the
    literal text. Missing keys render as ``<no name>`` for visibility.
    """
    def _sub(m: _re.Match[str]) -> str:
        key = m.group(1)
        v = context.get(key)
        if v is None:
            return f"<no {key}>"
        return str(v)
    try:
        return _PLACEHOLDER_RE.sub(_sub, template)
    except Exception:
        log.exception("template render failed: %r", template)
        return template


# ---- Filter matching ---------------------------------------------------


def _filters_match(filters: dict[str, Any] | None, ctx: dict[str, Any]) -> bool:
    """Every (k, v) in filters must equal ctx[k]. Missing keys → no match.

    Special key `min_level`: if present, only fire when ctx['level'] is
    at least this severe (notification < warning < error).
    """
    if not filters:
        return True
    LEVEL_RANK = {"notification": 0, "warning": 1, "error": 2}
    for key, expected in filters.items():
        if key == "min_level":
            actual_level = ctx.get("level", "notification")
            if LEVEL_RANK.get(actual_level, 0) < LEVEL_RANK.get(expected, 0):
                return False
            continue
        actual = ctx.get(key)
        if actual != expected:
            return False
    return True


# ---- Cooldown ----------------------------------------------------------


def _cooldown_target_key(ctx: dict[str, Any]) -> str:
    """Stable string identifying the "thing" the cooldown applies to.

    Cooldowns prevent spamming the same notification when an event
    fires repeatedly for the same target. We pick the most specific
    target available: node > group > pipeline > none.
    """
    return (
        ctx.get("node_id")
        or ctx.get("group_id")
        or ctx.get("pipeline_id")
        or "_global"
    )


# In-memory cooldown map. Keyed by (rule_id, target_key) → last fire time.
# Lives for the process lifetime; reset on restart. Acceptable
# trade-off — cooldowns are about avoiding spam, not strict enforcement.
_COOLDOWNS: dict[tuple[str, str], datetime] = {}


def _cooldown_blocks(rule: NotificationRule, ctx: dict[str, Any], now: datetime) -> bool:
    if not rule.cooldown_seconds:
        return False
    key = (rule.id, _cooldown_target_key(ctx))
    last = _COOLDOWNS.get(key)
    if last is None:
        return False
    return (now - last) < timedelta(seconds=rule.cooldown_seconds)


def _record_cooldown(rule: NotificationRule, ctx: dict[str, Any], now: datetime) -> None:
    if not rule.cooldown_seconds:
        return
    _COOLDOWNS[(rule.id, _cooldown_target_key(ctx))] = now


# ---- Main entrypoint ---------------------------------------------------


_VALID_LEVELS = ("notification", "warning", "error")


def _resolve_level(action_level: str, ctx: dict[str, Any]) -> str:
    if action_level == "auto":
        # Infer from event-kind heuristics. Producers can override via
        # ctx["level"] if they want explicit control.
        return ctx.get("level") or "notification"
    # Round-3 QA finding: rule definitions can use ``"{level}"`` as a
    # template placeholder to take the level FROM the event context.
    # Without rendering, the literal ``"{level}"`` flows through and
    # the storage layer silently coerces it to ``"notification"`` —
    # so a check_data violation tagged ``level="error"`` ended up as
    # an info-level notification. Render the template through the same
    # safe path used for title/message, then validate.
    rendered = _render(action_level, ctx)
    if rendered in _VALID_LEVELS:
        return rendered
    return "notification"


def _kind_for_notification(event_kind: str) -> str:
    """Map event kind back to the Notification.kind vocabulary so rows
    in the panel have a meaningful filter dimension. Same prefix
    extraction the UI uses."""
    base = event_kind.split(".", 1)[0]
    # Re-map a couple of cases where event prefix and notification kind
    # don't naturally line up.
    if base == "run":
        return "runtime"
    if base == "auth":
        return "login"
    return base


async def apply_rules_for_event(event_kind: str, context: dict[str, Any]) -> None:
    """Internal entrypoint called by emit_event(). Loads matching rules,
    evaluates them, fires notifications. Never raises (errors are
    logged + swallowed)."""
    try:
        async with SessionLocal() as session:
            res = await session.execute(
                select(NotificationRule).where(NotificationRule.enabled.is_(True))
            )
            rules = list(res.scalars().all())
    except Exception:
        log.exception("could not load notification rules; event %r dropped", event_kind)
        return

    now = datetime.now(timezone.utc)

    for rule in rules:
        if not event_kind_matches(rule.event_kind, event_kind):
            continue
        if not _filters_match(rule.filters, context):
            continue
        if _cooldown_blocks(rule, context, now):
            log.debug("rule %s cooldown blocks event %s", rule.id, event_kind)
            continue

        action = rule.action or {}
        title_t = action.get("title") or "{event_kind}"
        message_t = action.get("message")
        level = _resolve_level(action.get("level", "auto"), context)

        rendered_title = _render(title_t, {**context, "event_kind": event_kind})
        rendered_message = (
            _render(message_t, {**context, "event_kind": event_kind})
            if message_t else None
        )

        await record_notification(
            kind=_kind_for_notification(event_kind),
            level=level,
            title=rendered_title,
            message=rendered_message,
            user_id=context.get("user_id"),
            context={**context, "rule_id": rule.id, "rule_name": rule.name, "event_kind": event_kind},
        )

        # Stamp last_fired_at + bump fire_count + record cooldown.
        try:
            async with SessionLocal() as session:
                row = await session.get(NotificationRule, rule.id)
                if row:
                    row.last_fired_at = now
                    row.fire_count = (row.fire_count or 0) + 1
                    await session.commit()
        except Exception:
            log.exception("failed to bump fire_count for rule %s", rule.id)
        _record_cooldown(rule, context, now)


# ---- Default rules (seeded on startup) ---------------------------------


_DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "Run failed (any pipeline)",
        "description": "Error notification when any pipeline run fails.",
        "event_kind": EventKinds.RUN_FAILED,
        "filters": None,
        "action": {
            "level": "error",
            "title": "Pipeline run failed: {pipeline_name}",
            "message": "{error_type}: {error}",
            "channel": "in_app",
        },
        "cooldown_seconds": None,
    },
    {
        "name": "Freshness due (any group/node)",
        "description": "Warning when a node or group enters its warn-before-stale window.",
        "event_kind": EventKinds.FRESHNESS_DUE,
        "filters": None,
        "action": {
            "level": "warning",
            "title": "{target_label} is approaching stale",
            "message": "Last refreshed: {last_run_at}. SLA: {sla}.",
            "channel": "in_app",
        },
        "cooldown_seconds": 600,   # don't re-warn for the same target within 10m
    },
    {
        "name": "Freshness stale (any group/node)",
        "description": "Error when a node or group passes its SLA.",
        "event_kind": EventKinds.FRESHNESS_STALE,
        "filters": None,
        "action": {
            "level": "error",
            "title": "{target_label} is STALE",
            "message": "Last refreshed: {last_run_at}. SLA: {sla} (overdue).",
            "channel": "in_app",
        },
        "cooldown_seconds": 1800,  # one alert / 30m per target
    },
    {
        "name": "Data-quality check failed (any pipeline)",
        "description": "Surface every check_data violation as an in-app notification.",
        "event_kind": EventKinds.DATA_QUALITY_VIOLATION,
        "filters": None,
        "action": {
            "level": "{level}",
            "title": "{check_name}: {violations} violation(s)",
            "message": "Check kind: {check_kind} · {violations}/{total} rows failed in pipeline {pipeline_name}. Sample: {first_bad}",
            "channel": "in_app",
        },
        "cooldown_seconds": 60,    # short — users want fast feedback while iterating
    },
    {
        "name": "Schema drift detected (any pipeline)",
        "description": "Notify when a node's output column list changes between consecutive succeeded runs.",
        "event_kind": EventKinds.DATA_PROFILE_DRIFT,
        "filters": None,
        "action": {
            "level": "warning",
            "title": "Schema drift in {pipeline_name} · {node_id}",
            "message": "Columns {summary} between this run and the prior succeeded run.",
            "channel": "in_app",
        },
        "cooldown_seconds": 300,   # 5-min cooldown so an iterative editor doesn't get spammed
    },
    {
        "name": "Row-count anomaly (any pipeline)",
        "description": "Notify when a node's row count deviates ≥2σ from the historical average.",
        "event_kind": EventKinds.DATA_ROW_COUNT_ANOMALY,
        "filters": None,
        "action": {
            "level": "warning",
            "title": "Row-count anomaly in {pipeline_name} · {node_id}",
            "message": "{summary}. z-score {z_score} over the last {history_window} runs.",
            "channel": "in_app",
        },
        "cooldown_seconds": 300,
    },
]


async def seed_default_rules() -> None:
    """Idempotent — call from API startup. Adds any missing built-in
    rules without touching ones the user has customised."""
    try:
        async with SessionLocal() as session:
            existing = await session.execute(
                select(NotificationRule.name).where(NotificationRule.is_builtin.is_(True))
            )
            existing_names = {row[0] for row in existing.all()}
            for d in _DEFAULT_RULES:
                if d["name"] in existing_names:
                    continue
                session.add(NotificationRule(
                    id=str(ULID()),
                    name=d["name"],
                    description=d["description"],
                    enabled=True,
                    event_kind=d["event_kind"],
                    filters=d["filters"],
                    action=d["action"],
                    cooldown_seconds=d["cooldown_seconds"],
                    is_builtin=True,
                ))
            await session.commit()
    except Exception:
        log.exception("could not seed default notification rules")


# ---- REST endpoints ----------------------------------------------------


@router.get("", response_model=list[RuleOut])
async def list_rules(session: AsyncSession = Depends(get_session)) -> list[RuleOut]:
    res = await session.execute(
        select(NotificationRule).order_by(
            NotificationRule.is_builtin.desc(),  # built-ins first
            NotificationRule.created_at.desc(),
        )
    )
    return [_to_out(r) for r in res.scalars().all()]


@router.get("/event-kinds")
async def list_event_kinds() -> dict[str, list[str]]:
    """Returns the canonical event-kind vocabulary so the UI can populate
    the rule form's event picker without hardcoding."""
    return {"kinds": list(ALL_EVENT_KINDS) + ["*", "run.*", "freshness.*", "auth.*", "resources.*", "system.*"]}


@router.post("", response_model=RuleOut, status_code=201)
async def create_rule(
    body: RuleIn, session: AsyncSession = Depends(get_session)
) -> RuleOut:
    rid = str(ULID())
    row = NotificationRule(
        id=rid,
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        event_kind=body.event_kind,
        filters=body.filters,
        action=body.action.model_dump(),
        cooldown_seconds=body.cooldown_seconds,
        is_builtin=False,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.patch("/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: str, body: RuleIn, session: AsyncSession = Depends(get_session)
) -> RuleOut:
    row = await session.get(NotificationRule, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    row.name = body.name
    row.description = body.description
    row.enabled = body.enabled
    row.event_kind = body.event_kind
    row.filters = body.filters
    row.action = body.action.model_dump()
    row.cooldown_seconds = body.cooldown_seconds
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.patch("/{rule_id}/toggle", response_model=RuleOut)
async def toggle_rule(
    rule_id: str, session: AsyncSession = Depends(get_session)
) -> RuleOut:
    row = await session.get(NotificationRule, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    row.enabled = not row.enabled
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    row = await session.get(NotificationRule, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    if row.is_builtin:
        # Built-ins can be disabled but not deleted — otherwise the
        # next startup re-seeds them and the user's "delete" feels
        # like a no-op.
        raise HTTPException(
            400,
            "Built-in rule cannot be deleted. Disable it instead "
            "(or customise the action template).",
        )
    await session.delete(row)
    await session.commit()

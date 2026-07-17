"""Regression tests for three QA findings.

Each test pins the fix for a specific defect so it can't silently reopen:

  H1  schedules id-casing — the crontab marker is stored lowercased, so the
      list-parse path must normalise it back to the UPPERCASE ULID the
      validator (and the DELETE route) expect.
  M1  notification level normalization — a non-vocabulary level such as
      ``critical`` coming off an event context must land as ``notification``
      in the persisted row, not break the level whitelist.
  M2  runs boot sweep — a Run left at ``running`` by an unclean shutdown must
      be flipped to ``failed`` (with an error) by the startup sweep.

The schedules test monkeypatches the script runner so no real crontab is
touched; the notification/run tests bind the async engine + the API modules'
SessionLocal to a fresh per-test sqlite DB and drive the real code paths.
"""

from __future__ import annotations

import asyncio

import pytest
from ulid import ULID


# ---------------------------------------------------------------------------
# Shared DB harness — a fresh sqlite file, with every module-level
# ``SessionLocal`` binding repointed at it, all inside ONE event loop so the
# aiosqlite connections are never used across loops.
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_db, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from dig.storage import db as db_mod

    url = f"sqlite+aiosqlite:///{tmp_db}"
    engine = create_async_engine(url, future=True, connect_args={"timeout": 30})
    sm = async_sessionmaker(engine, expire_on_commit=False)

    # Repoint the canonical engine/sessionmaker and the copies the API
    # modules captured at import time (``from dig.storage.db import
    # SessionLocal``).
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal", sm)
    import dig.api.notification_rules as nr
    import dig.api.notifications as nt
    monkeypatch.setattr(nr, "SessionLocal", sm, raising=False)
    monkeypatch.setattr(nt, "SessionLocal", sm, raising=False)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(db_mod.init_db())
    try:
        yield sm, loop
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


# ---------------------------------------------------------------------------
# H1 — schedules id casing
# ---------------------------------------------------------------------------


def test_h1_validate_pipeline_id_is_uppercase_only():
    """The validator is the shape the DELETE route enforces; it accepts the
    canonical UPPERCASE ULID and rejects the lowercased marker form."""
    from dig.api import schedules

    pid = str(ULID())
    assert schedules._validate_pipeline_id(pid) == pid
    with pytest.raises(ValueError):
        schedules._validate_pipeline_id(pid.lower())


def test_h1_list_normalises_lowercase_marker_to_uppercase_id(monkeypatch):
    """A crontab line whose ``# DIG_SCHED:`` marker is lowercased must parse
    back to the UPPERCASE pipeline id so the row is API-manageable."""
    from dig.api import schedules

    pid = str(ULID())                       # Crockford base32, uppercase-canonical
    marker = pid.lower()                    # the form written into the crontab
    line = f"0 8 * * * {schedules._SCRIPT} run {pid} # DIG_SCHED:{marker}"

    async def _fake_run_script(args):
        assert args == ["list"]
        return (0, line + "\n", "")

    monkeypatch.setattr(schedules, "_run_script", _fake_run_script)

    entries = asyncio.run(schedules.list_schedules())
    assert len(entries) == 1
    assert entries[0].pipeline_id == pid    # normalised back to uppercase
    assert entries[0].cron == "0 8 * * *"
    assert entries[0].raw == line


# ---------------------------------------------------------------------------
# M1 — notification level normalization
# ---------------------------------------------------------------------------


def test_m1_event_critical_level_persists_as_notification(db):
    """An event tagged with the out-of-vocabulary level ``critical`` must be
    stored as ``notification`` — the persistence layer clamps to the
    ``notification | warning | error`` whitelist."""
    from sqlalchemy import select

    from dig.api import notification_rules as nr
    from dig.api.events import EventKinds
    from dig.storage.models import Notification, NotificationRule

    sm, loop = db

    async def _body():
        async with sm() as s:
            s.add(NotificationRule(
                id=str(ULID()),
                name="dq critical",
                description=None,
                enabled=True,
                event_kind=EventKinds.DATA_QUALITY_VIOLATION,
                filters=None,
                action={
                    "level": "auto",
                    "title": "{check_name}",
                    "message": None,
                    "channel": "in_app",
                },
                cooldown_seconds=None,
                is_builtin=False,
            ))
            await s.commit()

        nr._invalidate_rules_cache()
        await nr.apply_rules_for_event(
            EventKinds.DATA_QUALITY_VIOLATION,
            {"level": "critical", "pipeline_id": "p1", "check_name": "not_null"},
        )

        async with sm() as s:
            return (await s.execute(select(Notification))).scalars().all()

    rows = loop.run_until_complete(_body())
    assert len(rows) == 1
    assert rows[0].level == "notification"
    assert rows[0].title == "not_null"


# ---------------------------------------------------------------------------
# M2 — runs boot sweep
# ---------------------------------------------------------------------------


def test_m2_boot_sweep_fails_stranded_running_run(db):
    """A Run stuck at ``running`` from an unclean shutdown is flipped to
    ``failed`` (with an error message) by the lifespan startup sweep."""
    from dig.api.main import app, lifespan
    from dig.storage.models import Run

    sm, loop = db
    rid = str(ULID())

    async def _body():
        async with sm() as s:
            s.add(Run(id=rid, pipeline_id=str(ULID()), status="running"))
            await s.commit()

        # Run the real startup (which runs the sweep) then shut down.
        async with lifespan(app):
            pass

        async with sm() as s:
            return await s.get(Run, rid)

    row = loop.run_until_complete(_body())
    assert row is not None
    assert row.status == "failed"
    assert row.error == "interrupted by restart"
    assert row.finished_at is not None

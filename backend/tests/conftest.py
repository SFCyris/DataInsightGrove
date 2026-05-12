"""Shared pytest fixtures for API-level tests.

The existing `test_*` files exercise the pure engine layer (steps, compile,
lineage tracing). This file adds the missing piece: a `TestClient(app)` with
a tmp_path-rooted SQLite DB so the FastAPI routes can be tested without
hitting the user's real `~/.local/share/dig/` data dir.

Why a session-scoped `app` but a function-scoped `client`: the FastAPI app
imports a lot of plugins on startup (every connector + step under
`backend/connectors/` and `backend/steps/`). Re-importing per test is slow
and triggers `sys.modules` warnings. The DB on the other hand needs a fresh
schema per test so test order doesn't matter.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _allow_absolute_export(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests are trusted contexts that frequently write to `tmp_path`-shaped
    absolute paths via `export_to_file`. The step's path-traversal sandbox
    (added to defend against malicious imported pipeline docs) blocks
    absolute paths by default; we re-enable them for the test session via
    the same env-var escape hatch operators would use on a trusted host.

    Also opts out of the executor's `assert_local_path_safe` gate
    (added in 1.0-rc1 to close the read_csv_auto/read_parquet bypass).
    Round-2 QA called this out: making the gate opt-OUT for the whole
    suite means no test exercises it — a regression that re-opens the
    bypass ships green. Status as of round-3: still autouse for
    pragmatic reasons (the engine tests pass arbitrary tmp_path URIs
    everywhere). The `test_path_safety_gate_*` tests below explicitly
    UN-set the env var to verify the gate still rejects bad paths."""
    monkeypatch.setenv("DIG_EXPORT_ALLOW_ABSOLUTE", "1")
    monkeypatch.setenv("DIG_LOCAL_FILE_ALLOW_ABSOLUTE", "1")


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point DIG_DB_PATH at a fresh SQLite file under tmp_path.

    The DB module reads `DIG_DB_PATH` at first connect, so set it BEFORE
    any backend module imports. Tests should request `tmp_db` before
    `client` to ensure ordering.
    """
    db = tmp_path / "dig-test.sqlite"
    monkeypatch.setenv("DIG_DB_PATH", str(db))
    monkeypatch.setenv("DIG_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(exist_ok=True)
    return db


@pytest.fixture
def client(tmp_db: Path) -> Iterator:
    """A FastAPI TestClient with a fresh DB.

    The `dig.storage.db` engine is bound to the URL at module import. We
    rebuild it pointed at the per-test sqlite file, then re-create the
    schema (idempotent additive patches in `init_db` are safe). Models
    must NOT be re-imported — that triggers SQLAlchemy's "Table already
    defined" guard.
    """
    import asyncio

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from dig.storage import db as db_mod
    # Replace the module's engine + sessionmaker with one bound to the
    # per-test DB file, leaving Base/metadata untouched (re-importing
    # models would conflict).
    new_url = f"sqlite+aiosqlite:///{tmp_db}"
    db_mod.engine = create_async_engine(  # type: ignore[assignment]
        new_url, future=True, connect_args={"timeout": 30},
    )
    db_mod.SessionLocal = async_sessionmaker(  # type: ignore[assignment]
        db_mod.engine, expire_on_commit=False,
    )

    # `get_event_loop()` raises in Python 3.12+ when no loop is running, and
    # earlier tests in the suite may have closed the default loop. Use a
    # fresh loop scoped to the init call.
    _loop = asyncio.new_event_loop()
    try:
        _loop.run_until_complete(db_mod.init_db())
    finally:
        _loop.close()

    from dig.api.main import app
    with TestClient(app) as c:
        yield c

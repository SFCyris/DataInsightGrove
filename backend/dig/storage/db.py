from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _db_url() -> str:
    path = os.environ.get("DIG_DB_PATH")
    if not path:
        from dig.storage.files import data_dir

        path = str(data_dir() / "dig.sqlite")
    return f"sqlite+aiosqlite:///{path}"


engine = create_async_engine(
    _db_url(),
    echo=os.environ.get("DIG_DB_ECHO") == "1",
    future=True,
    connect_args={"timeout": 30},
)


@asynccontextmanager
async def _wal_setup() -> AsyncIterator[None]:
    """Enable WAL mode + sane pragmas on first connect.

    Safe to call repeatedly; pragmas are per-connection but SQLite stores the
    journal mode persistently in the database header.
    """
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    yield


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create tables if missing, apply WAL pragmas, and run any tiny one-shot
    schema patches for columns added in newer DIG versions.

    We don't ship Alembic yet (single-user dev tool). For the small set of
    additive changes, we just check `PRAGMA table_info(...)` and `ALTER TABLE
    ADD COLUMN` if missing. Drop this code once Alembic lands.
    """
    # Import models so their metadata registers on Base.
    from dig.storage import models  # noqa: F401

    async with _wal_setup():
        pass
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Additive patches — safe to re-run.
    patches: list[tuple[str, str, str]] = [
        # (table, column, "<col_name> <type>")
        ("datasets", "annotations", "annotations JSON"),
        ("runs",     "artifacts",   "artifacts JSON"),
    ]
    async with engine.begin() as conn:
        for table, column, decl in patches:
            res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
            existing = {row[1] for row in res.fetchall()}
            if column not in existing:
                try:
                    await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {decl}")
                except Exception:
                    # Best-effort: log but don't crash on startup.
                    import logging
                    logging.getLogger(__name__).exception(
                        "could not patch %s.%s — please reset data/ if errors persist", table, column
                    )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

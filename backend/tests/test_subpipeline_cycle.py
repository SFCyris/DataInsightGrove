"""Test subpipeline cycle detection.

A pipeline that references itself (directly or via a chain) must raise
RuntimeError instead of recursing forever. The check lives in the
subpipeline step's execute_polars + the executor's pipeline_chain context.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import polars as pl
import pytest
from ulid import ULID

from dig.engine.executor import execute
from dig.engine.pipeline import (
    DatasetSpec,
    Node,
    OutputSpec,
    Pipeline,
    Reference,
)
from dig.storage import db as db_mod  # noqa: F401  (used inside async fns via db_mod.SessionLocal)
from dig.storage.models import Pipeline as PipelineRow


@pytest.fixture
def csv_path(tmp_path) -> Path:
    p = tmp_path / "tiny.csv"
    p.write_text("id,name\n1,a\n2,b\n3,c\n")
    return p


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Use a per-test SQLite so test pipelines don't pollute the dev DB.

    Patch the db module's engine in-place — reloading the module would
    create a fresh Base class with empty metadata, leaving any test that
    runs afterward with no tables registered against the new Base.
    """
    db = tmp_path / "test.sqlite"
    monkeypatch.setenv("DIG_DB_PATH", str(db))
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from dig.storage import db as db_mod
    new_url = f"sqlite+aiosqlite:///{db}"
    db_mod.engine = create_async_engine(new_url, future=True, connect_args={"timeout": 30})
    db_mod.SessionLocal = async_sessionmaker(db_mod.engine, expire_on_commit=False)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(db_mod.init_db())
    finally:
        loop.close()
    yield


def _run_async(coro):
    """Run a coroutine on a fresh event loop. ``asyncio.get_event_loop()``
    is deprecated since 3.10 (DeprecationWarning) and raises in 3.12+
    when there is no current loop — use a dedicated runner per call."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _save_pipeline(p: Pipeline) -> str:
    """Persist a pipeline doc to the DB; returns id."""
    async def _go():
        async with db_mod.SessionLocal() as session:
            row = PipelineRow(
                id=p.id, name=p.name, document=p.model_dump(by_alias=True), etag=1,
            )
            session.add(row)
            await session.commit()
        return p.id
    return _run_async(_go())


def _passthrough_pipeline(uri: str) -> Pipeline:
    return Pipeline(
        id=str(ULID()), name="t",
        datasets=[DatasetSpec(id="ds", connector="csv", uri=f"file://{uri}")],
        nodes=[Node(
            id="n", step="filter_rows", stepVersion="1.0.0",
            inputs={"in": Reference(ref="ds")}, params={"predicate": "TRUE"},
        )],
        outputs=[OutputSpec(id="o", name="out",
                            **{"from": Reference(ref="n", port="out")})],
    )


def test_subpipeline_cycle_self_reference(csv_path, monkeypatch, tmp_path):
    from dig.storage import files as files_mod
    monkeypatch.setattr(files_mod, "data_dir", lambda: tmp_path)

    # Build pipeline P that contains a subpipeline node referencing P itself.
    inner = _passthrough_pipeline(str(csv_path))
    pid = _save_pipeline(inner)

    # Now patch the saved doc to ADD a subpipeline node referencing itself.
    async def _patch():
        async with db_mod.SessionLocal() as session:
            row = await session.get(PipelineRow, pid)
            doc = dict(row.document)
            doc["nodes"] = doc.get("nodes", []) + [{
                "id": "n_self", "step": "subpipeline", "stepVersion": "1.0.0",
                "inputs": {}, "outputs": ["out"],
                "params": {"pipeline_id": pid},
            }]
            doc["outputs"] = [{
                "id": "o", "name": "out",
                "from": {"ref": "n_self", "port": "out"},
            }]
            row.document = doc
            await session.commit()
    _run_async(_patch())

    # Re-load + execute. Should raise (or fail run) cleanly, not recurse.
    async def _load_and_run():
        async with db_mod.SessionLocal() as session:
            row = await session.get(PipelineRow, pid)
            return Pipeline.model_validate(row.document)

    p2 = _run_async(_load_and_run())
    with pytest.raises(Exception) as exc:
        execute(p2, run_id=str(ULID()))
    msg = str(exc.value).lower()
    assert "cycle" in msg or "subpipeline" in msg, f"expected cycle/subpipeline in error, got: {exc.value}"

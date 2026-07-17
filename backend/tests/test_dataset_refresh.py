"""Tests for POST /datasets/{id}/refresh — the in-place re-ingest path.

Covers the two integrity guards on the refresh handler in
``dig/api/datasets.py``:

  - the compare-and-set 409 lock that stops two concurrent refreshes from
    both claiming a row (status flips ``* -> ingesting`` in one UPDATE);
  - the atomic parquet write in ``_write_parquet_atomic`` (temp file +
    ``os.replace``) that never truncates the live cache and leaves no
    ``*.tmp-*`` residue on either the success or the failure path.

Plus the two request-validation branches (409 already-in-progress, 400
missing source_uri).

The suite drives the real FastAPI app via the conftest ``client`` fixture
(TestClient + per-test tmp SQLite + tmp DIG_DATA_DIR), uploads a small CSV
to get a genuine ``ready`` dataset with a materialised parquet, then pokes
row status / the source file / ``pl.DataFrame.write_parquet`` to exercise
each branch.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import polars as pl
import pytest

from dig.storage import db as db_mod
from dig.storage.files import cached_parquet_path
from dig.storage.models import Dataset


def _run_async(coro):
    """Run a coroutine on a dedicated event loop.

    ``asyncio.get_event_loop()`` raises in 3.12+ when no loop is running and
    the TestClient may have left the default loop closed — use a fresh loop
    per call, matching the pattern in ``test_subpipeline_cycle.py``.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _set_status(dataset_id: str, status: str) -> None:
    """Force a dataset's status directly via the ORM + commit."""
    async def _go():
        async with db_mod.SessionLocal() as session:
            d = await session.get(Dataset, dataset_id)
            d.status = status
            await session.commit()
    _run_async(_go())


def _get_status(dataset_id: str) -> str:
    async def _go():
        async with db_mod.SessionLocal() as session:
            d = await session.get(Dataset, dataset_id)
            return d.status
    return _run_async(_go())


def _upload_csv(client, body: bytes, name: str) -> dict:
    """Upload a CSV and return the (ready) dataset DTO."""
    resp = client.post(
        "/datasets",
        files={"file": (f"{name}.csv", body, "text/csv")},
        data={"name": name, "connector_id": "csv"},
    )
    assert resp.status_code == 200, resp.text
    dto = resp.json()
    assert dto["status"] == "ready", dto
    return dto


_CSV_3ROWS = b"id,name\n1,a\n2,b\n3,c\n"
_CSV_5ROWS = b"id,name\n1,a\n2,b\n3,c\n4,d\n5,e\n"


def test_refresh_409_when_already_ingesting(client) -> None:
    """A row already in status='ingesting' cannot be claimed again: the
    compare-and-set UPDATE matches 0 rows -> 409 'refresh already in
    progress'. Restoring status='ready' lets a subsequent refresh proceed."""
    dto = _upload_csv(client, _CSV_3ROWS, "refresh-409")
    ds_id = dto["id"]

    _set_status(ds_id, "ingesting")
    resp = client.post(f"/datasets/{ds_id}/refresh")
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "refresh already in progress"

    # The failed claim must not have mutated status away from ingesting.
    assert _get_status(ds_id) == "ingesting"

    # Restore and confirm the lock releases — a real refresh now succeeds.
    _set_status(ds_id, "ready")
    ok = client.post(f"/datasets/{ds_id}/refresh")
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "ready"


def test_refresh_atomic_success_updates_rowcount_no_tmp_residue(client) -> None:
    """Mutating the source file then refreshing re-materialises the parquet:
    rowCount picks up the new rows, the cached parquet exists, and no
    ``*.tmp-*`` temp file is left behind by the atomic write."""
    dto = _upload_csv(client, _CSV_3ROWS, "refresh-atomic")
    ds_id = dto["id"]
    assert dto["rowCount"] == 3

    cached = cached_parquet_path(ds_id)
    assert cached.exists()

    # Mutate the source file the dataset points at (adds two rows).
    source_path = Path(dto["sourceUri"].replace("file://", ""))
    assert source_path.exists()
    source_path.write_bytes(_CSV_5ROWS)

    resp = client.post(f"/datasets/{ds_id}/refresh")
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["status"] == "ready"
    assert out["rowCount"] == 5

    # Parquet is present and no temp residue remains in its directory.
    assert cached.exists()
    assert sorted(cached.parent.glob("*.tmp-*")) == []


def test_refresh_failure_preserves_cache_and_leaves_no_tmp(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the parquet write raises mid-refresh, status ends 'failed', the
    PRE-EXISTING cached parquet is byte-for-byte unchanged (os.replace never
    ran), and the aborted temp file is cleaned up (no ``*.tmp-*`` residue)."""
    dto = _upload_csv(client, _CSV_3ROWS, "refresh-fail")
    ds_id = dto["id"]

    cached = cached_parquet_path(ds_id)
    original_bytes = cached.read_bytes()

    # Mutate the source so a successful refresh WOULD change the parquet —
    # this makes "bytes unchanged" a meaningful assertion (proves the old
    # file survived rather than being coincidentally identical).
    source_path = Path(dto["sourceUri"].replace("file://", ""))
    source_path.write_bytes(_CSV_5ROWS)

    def _boom(self, target, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        # Write the half-baked temp file the atomic writer handed us, THEN
        # raise — so the except-branch's ``tmp.unlink`` cleanup is genuinely
        # exercised (a mock that raises before touching disk would leave no
        # residue regardless of whether the cleanup runs).
        Path(target).write_bytes(b"partial-parquet-garbage")
        raise RuntimeError("simulated write_parquet failure")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _boom)

    resp = client.post(f"/datasets/{ds_id}/refresh")
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["status"] == "failed"
    assert "simulated write_parquet failure" in (out["error"] or "")
    # rowCount must NOT have advanced to the mutated file's 5 rows.
    assert out["rowCount"] == 3

    # Pre-existing cache untouched + no temp residue.
    assert cached.read_bytes() == original_bytes
    assert sorted(cached.parent.glob("*.tmp-*")) == []


def test_refresh_400_when_no_source_uri(client) -> None:
    """A dataset with an empty source_uri has nothing to refresh from -> 400.
    The check fires before the concurrency claim, so status is untouched."""
    ds_id = "01J000000000000000000NOSRC"

    async def _seed():
        async with db_mod.SessionLocal() as session:
            session.add(Dataset(
                id=ds_id,
                name="no-source",
                connector="csv",
                source_uri="",
                status="ready",
            ))
            await session.commit()
    _run_async(_seed())

    resp = client.post(f"/datasets/{ds_id}/refresh")
    assert resp.status_code == 400, resp.text
    assert "source_uri" in resp.json()["detail"]
    assert _get_status(ds_id) == "ready"

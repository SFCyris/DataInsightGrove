"""Regressions for the P1 defects from the 2026-07-17 design/UX/flow review."""

from __future__ import annotations

from pathlib import Path

import pytest

from dig.engine.cancellation import (
    RunCancelled,
    clear,
    is_cancelled,
    raise_if_cancelled,
    request_cancel,
)


# --------------------------------------------------------------------------
# P1-9 — "Cancel run" must actually stop the run
# --------------------------------------------------------------------------

def test_cancellation_flag_lifecycle() -> None:
    assert not is_cancelled("R")
    request_cancel("R")
    assert is_cancelled("R")
    with pytest.raises(RunCancelled):
        raise_if_cancelled("R")
    clear("R")
    assert not is_cancelled("R")
    # Cleared flags must not linger — a recycled run id would otherwise
    # inherit a cancellation it never asked for.
    raise_if_cancelled("R")


def _tiny_pipeline(pid: str, csv: Path) -> dict:
    return {
        "schemaVersion": 1, "id": pid, "name": "cancel-test",
        "datasets": [{"id": "ds", "connector": "csv", "uri": f"file://{csv}"}],
        "nodes": [{"id": "n1", "step": "filter_rows", "stepVersion": "1.0.0",
                   "inputs": {"in": {"ref": "ds"}}, "params": {"predicate": "val > 5"}}],
        "outputs": [{"id": "o", "name": "out", "from": {"ref": "n1"}}],
    }


def test_cancelled_run_stops_before_writing_output(tmp_db: Path, tmp_path: Path) -> None:
    """A cancelled run must not write its output — including its sink.

    `task.cancel()` only unwinds the awaiting coroutine; it cannot interrupt
    the worker thread running the executor. Before the cooperative checkpoints
    the run kept going and its writes still landed *after* the UI reported
    "cancelled".
    """
    from dig.engine.executor import execute
    from dig.engine.pipeline import Pipeline
    from dig.storage.files import data_dir

    csv = tmp_path / "n.csv"
    csv.write_text("id,val\n1,3\n2,90\n3,120\n")
    p = Pipeline.model_validate(_tiny_pipeline("01AAAAAAAAAAAAAAAAAAAAAAAA", csv))

    request_cancel("RUN_CANCEL")
    try:
        with pytest.raises(RunCancelled):
            execute(p, run_id="RUN_CANCEL")
        out_dir = data_dir() / "outputs" / "RUN_CANCEL"
        written = list(out_dir.glob("*.parquet")) if out_dir.exists() else []
        assert written == [], f"cancelled run still wrote {written}"
    finally:
        clear("RUN_CANCEL")


def test_uncancelled_run_completes(tmp_db: Path, tmp_path: Path) -> None:
    """The checkpoints must not break a normal run."""
    from dig.engine.executor import execute
    from dig.engine.pipeline import Pipeline

    csv = tmp_path / "n.csv"
    csv.write_text("id,val\n1,3\n2,90\n3,120\n")
    p = Pipeline.model_validate(_tiny_pipeline("01BBBBBBBBBBBBBBBBBBBBBBBB", csv))
    res = execute(p, run_id="RUN_OK_P1")
    assert Path(res.outputs["o"]).exists()
    assert res.rowCounts["o"] == 2  # val > 5


# --------------------------------------------------------------------------
# P1-11 — the etag check must be atomic
# --------------------------------------------------------------------------

def test_concurrent_saves_cannot_both_win(client, tmp_path) -> None:
    """Two saves from the same etag: exactly one succeeds, the other 409s.

    The old read-compare-write let both pass the check and both commit, so one
    user's save silently overwrote the other's.
    """
    pid = client.post("/pipelines", json={"name": "etag", "document": None}).json()["id"]

    def doc(name: str) -> dict:
        return {"schemaVersion": 1, "id": pid, "name": name,
                "datasets": [], "nodes": [], "outputs": []}

    first = client.put(f"/pipelines/{pid}", json={"document": doc("A"), "expectedEtag": 1})
    assert first.status_code == 200, first.text
    # Second writer still holding the pre-first etag.
    second = client.put(f"/pipelines/{pid}", json={"document": doc("B"), "expectedEtag": 1})
    assert second.status_code == 409, second.text
    # The winner's document survived.
    assert client.get(f"/pipelines/{pid}").json()["document"]["name"] == "A"

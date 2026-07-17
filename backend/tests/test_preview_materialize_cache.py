"""Regression tests for the live-preview materialization cache.

Focusing a node whose upstream chain contains a Polars step used to re-run
``execute_polars`` for every ancestor on every focus — invisible on tiny
fixtures (~15 ms) but seconds on real geometry/large data, so going back and
forth between nodes felt slow every time. ``materialize_polars_ancestors`` now
fingerprints each Polars ancestor (step + params + sample size + the mtime/size
of every source/upstream file its input SQL reads), bakes that fingerprint into
the parquet filename, and reuses the on-disk file when the fingerprint is
unchanged.

These tests assert the *behaviour that makes it fast*: a warm re-focus must
reuse the same fingerprinted parquet without rewriting it (proof it wasn't
re-executed), and a source change must produce a new fingerprinted parquet with
different bytes (proof the cache invalidates correctly).
"""

from __future__ import annotations

import os
from pathlib import Path


def _write_series_csv(tmp_path: Path, vals: list[int]) -> Path:
    csv = tmp_path / "series.csv"
    lines = ["id,val"] + [f"{i + 1},{v}" for i, v in enumerate(vals)]
    csv.write_text("\n".join(lines) + "\n")
    return csv


def _create_two_polars_chain(client, csv_path: Path) -> str:
    """CSV → n_roll (rolling, Polars) → n_roll2 (rolling, Polars, terminal).

    Focusing n_roll2 materialises n_roll — the ancestor we watch for reuse.
    """
    r = client.post("/pipelines", json={"name": "mat-cache", "document": None})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    doc = {
        "schemaVersion": 1,
        "id": pid,
        "name": "mat-cache",
        "datasets": [{"id": "ds", "connector": "csv", "uri": f"file://{csv_path}"}],
        "nodes": [
            {
                "id": "n_roll",
                "step": "rolling",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": "ds"}},
                "params": {"windows": [{"column": "val", "fn": "mean", "window": 3, "as": "val_ma"}]},
            },
            {
                "id": "n_roll2",
                "step": "rolling",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": "n_roll"}},
                "params": {"windows": [{"column": "val_ma", "fn": "sum", "window": 2, "as": "val_ma_sum"}]},
            },
        ],
        "outputs": [{"id": "o", "name": "out", "from": {"ref": "n_roll2"}}],
    }
    r = client.put(f"/pipelines/{pid}", json={"document": doc, "expectedEtag": 1})
    assert r.status_code == 200, r.text
    return pid


def _focus(client, pid: str, terminal: str = "n_roll2", **params) -> None:
    r = client.post(
        f"/pipelines/{pid}/preview-step-rows",
        params={"terminal": terminal, **params},
    )
    assert r.status_code == 200, r.text


def _ancestor_parquets(tmp_path: Path, pid: str, node: str = "n_roll") -> list[Path]:
    """All fingerprint-named parquets for the given ancestor node."""
    d = tmp_path / "data" / "outputs" / "__preview" / pid
    return sorted(d.glob(f"{node}.*.parquet")) if d.exists() else []


def test_warm_refocus_does_not_reexecute_polars_ancestor(client, tmp_path) -> None:
    """Cold focus materialises the ancestor; a warm re-focus reuses it.

    Falsifying test: if the cache were absent, the warm focus would re-run the
    Polars ancestor and rewrite its parquet, changing st_mtime_ns. We assert the
    same single fingerprinted file is reused, byte-for-byte, mtime unchanged.
    """
    csv = _write_series_csv(tmp_path, [10, 20, 30, 40, 50, 60, 70])
    pid = _create_two_polars_chain(client, csv)

    # Cold: nothing cached yet.
    assert _ancestor_parquets(tmp_path, pid) == []
    _focus(client, pid)
    cold = _ancestor_parquets(tmp_path, pid)
    assert len(cold) == 1, "cold focus must materialise exactly one ancestor parquet"
    cold_path = cold[0]
    cold_mtime = os.stat(cold_path).st_mtime_ns

    # Warm re-focus (identical request): reuse the same file, do not rebuild.
    _focus(client, pid)
    warm = _ancestor_parquets(tmp_path, pid)
    assert warm == [cold_path], "warm re-focus must reuse the same fingerprinted file"
    assert os.stat(cold_path).st_mtime_ns == cold_mtime, (
        "warm re-focus rewrote the ancestor parquet — the Polars step was "
        "re-executed instead of reusing the cache"
    )

    # A third identical focus is still a hit (no drift).
    _focus(client, pid)
    assert _ancestor_parquets(tmp_path, pid) == [cold_path]
    assert os.stat(cold_path).st_mtime_ns == cold_mtime


def test_source_change_busts_the_cache(client, tmp_path) -> None:
    """Editing the source CSV must invalidate the cached ancestor parquet.

    Cold/warm-with-*different-input* discipline: the fingerprint folds in the
    source file's mtime+size, so re-focusing after the data changes produces a
    *new* fingerprinted parquet whose bytes differ from the first.
    """
    csv = _write_series_csv(tmp_path, [10, 20, 30, 40, 50, 60, 70])
    pid = _create_two_polars_chain(client, csv)

    _focus(client, pid)
    first = _ancestor_parquets(tmp_path, pid)
    assert len(first) == 1
    first_path = first[0]
    first_bytes = first_path.read_bytes()

    # Change the source data (different values → different rolling output),
    # and force a strictly-later mtime so the change is unambiguous.
    _write_series_csv(tmp_path, [1, 2, 3, 4, 5, 6, 7])
    st = os.stat(csv)
    os.utime(csv, ns=(st.st_mtime_ns + 1_000_000_000, st.st_mtime_ns + 1_000_000_000))

    _focus(client, pid)
    after = _ancestor_parquets(tmp_path, pid)
    new_files = [p for p in after if p != first_path]
    assert new_files, "source changed but no new fingerprinted ancestor parquet appeared"
    assert new_files[0].read_bytes() != first_bytes, (
        "new ancestor parquet has identical bytes after a source change — the "
        "cache served stale data"
    )


def test_same_size_source_edit_with_restored_mtime_busts_cache(client, tmp_path) -> None:
    """A same-byte-size content edit that resets mtime must still bust the cache.

    mtime+size alone would collide (the failure a QA pass reproduced); the
    fingerprint also folds in ctime, which the kernel bumps on every write and
    userspace cannot forge. cp -p / rsync --times / restore-from-backup all hit
    this. Values keep the same digit-width so the CSV byte length is identical.
    """
    csv = _write_series_csv(tmp_path, [10, 20, 30, 40, 50, 60, 70])
    size_before = csv.stat().st_size
    pid = _create_two_polars_chain(client, csv)

    _focus(client, pid)
    first = _ancestor_parquets(tmp_path, pid)
    assert len(first) == 1
    first_path = first[0]
    orig_mtime = os.stat(csv).st_mtime_ns

    # Different content, identical byte length; restore the original mtime.
    _write_series_csv(tmp_path, [11, 21, 31, 41, 51, 61, 71])
    assert csv.stat().st_size == size_before, "test setup: byte size must be unchanged"
    os.utime(csv, ns=(orig_mtime, orig_mtime))
    assert os.stat(csv).st_mtime_ns == orig_mtime, "test setup: mtime must be restored"

    _focus(client, pid)
    after = _ancestor_parquets(tmp_path, pid)
    assert any(p != first_path for p in after), (
        "same-size edit with restored mtime did not bust the cache — mtime+size "
        "collision serving stale data (ctime must be in the fingerprint)"
    )


def test_sample_rows_change_produces_distinct_cache_entry(client, tmp_path) -> None:
    """Different sample_rows caps must key distinct cache files.

    Guards against a smaller-sample materialization being served for a request
    that asked for more rows.
    """
    csv = _write_series_csv(tmp_path, [10, 20, 30, 40, 50, 60, 70])
    pid = _create_two_polars_chain(client, csv)

    _focus(client, pid, sample_rows=3)
    _focus(client, pid, sample_rows=20_000)
    files = _ancestor_parquets(tmp_path, pid)
    assert len(files) == 2, (
        f"expected two distinct cache files for two sample_rows caps, got {len(files)}"
    )


def _create_nondet_chain(client, csv_path: Path) -> str:
    """CSV → n_rt (add_runtime_column, declared non-deterministic) → n_roll2."""
    r = client.post("/pipelines", json={"name": "nondet", "document": None})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    doc = {
        "schemaVersion": 1,
        "id": pid,
        "name": "nondet",
        "datasets": [{"id": "ds", "connector": "csv", "uri": f"file://{csv_path}"}],
        "nodes": [
            {
                "id": "n_rt",
                "step": "add_runtime_column",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": "ds"}},
                "params": {"name": "stamp", "template": "{{ utime }}", "columnType": "string"},
            },
            {
                "id": "n_roll2",
                "step": "rolling",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": "n_rt"}},
                "params": {"windows": [{"column": "val", "fn": "sum", "window": 2, "as": "val_s"}]},
            },
        ],
        "outputs": [{"id": "o", "name": "out", "from": {"ref": "n_roll2"}}],
    }
    r = client.put(f"/pipelines/{pid}", json={"document": doc, "expectedEtag": 1})
    assert r.status_code == 200, r.text
    return pid


def test_nondeterministic_ancestor_is_never_cached(client, tmp_path) -> None:
    """A step declaring engine.deterministic=false must re-execute every focus.

    Otherwise a wall-clock column (``{{ utime }}``) would freeze until restart.
    The ancestor writes a single stable ``<node>.nondet.parquet`` (never a
    fingerprint-named file), rewritten in place on each focus.
    """
    csv = _write_series_csv(tmp_path, [10, 20, 30, 40, 50, 60, 70])
    pid = _create_nondet_chain(client, csv)
    preview_dir = tmp_path / "data" / "outputs" / "__preview" / pid

    _focus(client, pid)
    # The only materialization is the stable nondet file — never a
    # fingerprint-named cache entry.
    stable = preview_dir / "n_rt.nondet.parquet"
    assert _ancestor_parquets(tmp_path, pid, node="n_rt") == [stable], (
        "non-deterministic ancestor was cached under a fingerprint name"
    )
    m1 = os.stat(stable).st_mtime_ns

    # Force a distinct mtime tick so re-execution is observable, then re-focus.
    os.utime(stable, ns=(m1 - 5_000_000_000, m1 - 5_000_000_000))
    _focus(client, pid)
    assert os.stat(stable).st_mtime_ns != m1 - 5_000_000_000, (
        "non-deterministic ancestor was not re-executed on re-focus (served cache)"
    )

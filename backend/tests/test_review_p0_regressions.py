"""Regressions for the P0 defects found in the 2026-07-17 design/UX/flow review.

Two backend-side fixes are covered here:

* **Sink writes can no longer clobber input data.** ``o.sink.uri`` is a
  free-form string carried in the pipeline document, so it arrives
  unvalidated from an imported ``.dig.json`` or a forked template. The read
  allow-list was not sufficient: it permits all of ``data_dir()``, which
  *contains* ``uploads/`` — the user's own source files.

* **Compile can use the caller's in-flight document.** The editor previews on
  a 350ms debounce while autosave runs on 500ms, so compiling from storage
  rendered the previous edit. ``POST /pipelines/{id}/compile`` now accepts an
  optional ``document``; omitting it keeps the original behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dig.engine.executor import _is_local_file_uri
from dig.engine.uri_safety import assert_write_target_safe
from dig.storage.files import data_dir

# --------------------------------------------------------------------------
# Sink write guard
# --------------------------------------------------------------------------

def test_write_guard_blocks_user_uploads(tmp_db: Path) -> None:
    """A sink pointing at the user's own uploaded source file is refused.

    This is the failure that motivated the guard: `uploads/` sits *inside*
    `data_dir()`, so the read-oriented check passed it straight through and
    the connector truncated the source file in place.
    """
    target = data_dir() / "uploads" / "ds_123-sales.csv"
    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(str(target))
    # …and via a file:// URI, which is how sinks are usually written.
    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(f"file://{target}")


def test_write_guard_blocks_dataset_cache_and_catalog(tmp_db: Path) -> None:
    """The ingested parquet cache and the sqlite catalog are equally off-limits."""
    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(str(data_dir() / "datasets" / "ds_123.parquet"))
    with pytest.raises(ValueError, match="catalog database"):
        assert_write_target_safe(str(data_dir() / "dig.sqlite"))


@pytest.mark.parametrize("variant", ["uploads", "UPLOADS", "UpLoAdS", "Uploads"])
def test_write_guard_is_case_insensitive_for_inputs(tmp_db: Path, variant: str) -> None:
    """Case variants must be refused too.

    The first version of this guard compared with ``Path.relative_to``, which
    is exact and case-sensitive, while the candidate path had already been
    ``resolve()``d. On a case-insensitive volume — APFS/macOS by default, and
    this project ships a Mac wrapper — ``data/UPLOADS/x.csv`` slipped past the
    check and the write then landed on the real ``data/uploads/x.csv``,
    destroying the user's source file. Refusing a genuinely distinct
    ``UPLOADS/`` on a case-sensitive volume is the safe direction to err.
    """
    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(str(data_dir() / variant / "source.csv"))


@pytest.mark.parametrize(
    "name",
    [
        "dig.sqlite", "DIG.SQLITE", "Dig.SqLite",     # the catalog, any casing
        "catalog.db", "catalog.DB",
        "other.sqlite3", "warehouse.duckdb", "WAREHOUSE.DuckDB",
        "dig.sqlite-wal", "foo.sqlite-shm", "bar.db-journal",  # sidecars
    ],
)
def test_write_guard_blocks_database_files_any_casing(tmp_db: Path, name: str) -> None:
    """Database files and their sidecars are never valid pipeline output.

    Truncating a ``-wal``/``-shm``/``-journal`` corrupts the database as
    surely as truncating the main file, and the original check missed both
    those and every non-lowercase spelling.
    """
    # The catalog gets its own message — it is refused even for export_to_db,
    # which is otherwise allowed to create database files.
    expected = "catalog database" if name.casefold().startswith("dig.sqlite") else "database file"
    with pytest.raises(ValueError, match=expected):
        assert_write_target_safe(str(data_dir() / name))


def test_write_guard_follows_symlinked_input_roots(tmp_db: Path) -> None:
    """A symlinked ``uploads/`` must still be protected, from either path.

    With unresolved protected roots, a candidate that resolved *through* the
    symlink no longer matched the root prefix and was allowed through.
    """
    d = data_dir()
    real = d / "store" / "uploads"
    real.mkdir(parents=True, exist_ok=True)
    link = d / "uploads"
    if link.exists() and not link.is_symlink():
        import shutil
        shutil.rmtree(link)
    if not link.exists():
        link.symlink_to(real, target_is_directory=True)

    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(str(link / "source.csv"))
    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(str(real / "source.csv"))


def test_write_guard_does_not_overmatch_on_name_prefix(tmp_db: Path) -> None:
    """`outputs/uploadsX/` merely *starts with* a protected name — allow it.

    Guards against fixing the case bypass by switching to a naive string
    prefix test, which would refuse legitimate destinations.
    """
    ok = data_dir() / "outputs" / "uploadsX" / "result.csv"
    assert assert_write_target_safe(str(ok)) == ok.resolve()


def test_write_guard_allows_run_outputs(tmp_db: Path) -> None:
    """The legitimate destination still works — the guard must not block real exports."""
    out = data_dir() / "outputs" / "run-1" / "result.csv"
    assert assert_write_target_safe(str(out)) == out.resolve()


def test_export_hatch_widens_destinations_but_never_unlocks_inputs(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``DIG_EXPORT_ALLOW_ABSOLUTE`` is about *where output may go*.

    It must never become a licence to destroy an input — "input data is
    sacred" is unconditional, so the protected roots stay refused even with
    the hatch set.
    """
    monkeypatch.setenv("DIG_EXPORT_ALLOW_ABSOLUTE", "1")
    # Outside the data dir: now permitted.
    assert assert_write_target_safe("/tmp/dig-export-check.csv")
    # Inside uploads/: still refused.
    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(str(data_dir() / "uploads" / "ds_1-src.csv"))


def test_read_hatch_does_not_authorise_writes(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read hatch is documented for reads; it must not widen writes."""
    monkeypatch.setenv("DIG_LOCAL_FILE_ALLOW_ABSOLUTE", "1")
    monkeypatch.delenv("DIG_EXPORT_ALLOW_ABSOLUTE", raising=False)
    with pytest.raises(ValueError, match="outside the allowed roots"):
        assert_write_target_safe("/tmp/should-not-be-writable.csv")


@pytest.mark.parametrize(
    "uri,is_local",
    [
        ("/tmp/a.csv", True),
        ("file:///tmp/a.csv", True),
        (r"C:\data\a.csv", True),          # Windows drive letter parses as a 1-char scheme
        ("postgres://host/db", False),
        ("s3://bucket/key.csv", False),
        ("https://example.com/x.csv", False),
    ],
)
def test_local_file_uri_detection(uri: str, is_local: bool) -> None:
    """Only local targets are guardable here; remote connectors own their own auth."""
    assert _is_local_file_uri(uri) is is_local


# --------------------------------------------------------------------------
# Compile from the in-flight document
# --------------------------------------------------------------------------

def _pipeline_with_predicate(pid: str, csv: Path, predicate: str) -> dict:
    return {
        "schemaVersion": 1,
        "id": pid,
        "name": "compile-doc",
        "datasets": [{"id": "ds", "connector": "csv", "uri": f"file://{csv}"}],
        "nodes": [
            {
                "id": "n_f",
                "step": "filter_rows",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": "ds"}},
                "params": {"predicate": predicate},
            }
        ],
        "outputs": [{"id": "o", "name": "out", "from": {"ref": "n_f"}}],
    }


def test_compile_prefers_the_supplied_document(client, tmp_path) -> None:
    """With a body, compile reflects the user's unsaved edits.

    Falsifying check: the SQL must contain the *unsaved* predicate and must
    NOT contain the saved one — otherwise the preview is still rendering the
    previous state, which is the bug.
    """
    csv = tmp_path / "n.csv"
    csv.write_text("id,val\n1,10\n2,90\n")
    pid = client.post("/pipelines", json={"name": "compile-doc", "document": None}).json()["id"]
    saved = _pipeline_with_predicate(pid, csv, "val > 80")
    resp = client.put(f"/pipelines/{pid}", json={"document": saved, "expectedEtag": 1})
    assert resp.status_code == 200

    unsaved = _pipeline_with_predicate(pid, csv, "val > 20")
    r = client.post(
        f"/pipelines/{pid}/compile", params={"terminal": "n_f"}, json={"document": unsaved}
    )
    assert r.status_code == 200, r.text
    sql = r.json()["sql"]
    assert "val > 20" in sql
    assert "val > 80" not in sql


def test_compile_without_body_uses_stored_document(client, tmp_path) -> None:
    """Omitting the body keeps the original behaviour — no caller has to change."""
    csv = tmp_path / "n.csv"
    csv.write_text("id,val\n1,10\n2,90\n")
    pid = client.post("/pipelines", json={"name": "compile-doc", "document": None}).json()["id"]
    saved = _pipeline_with_predicate(pid, csv, "val > 80")
    resp = client.put(f"/pipelines/{pid}", json={"document": saved, "expectedEtag": 1})
    assert resp.status_code == 200

    r = client.post(f"/pipelines/{pid}/compile", params={"terminal": "n_f"})
    assert r.status_code == 200, r.text
    assert "val > 80" in r.json()["sql"]


def test_compile_does_not_persist_the_supplied_document(client, tmp_path) -> None:
    """Compile is read-only: previewing an edit must never save it."""
    csv = tmp_path / "n.csv"
    csv.write_text("id,val\n1,10\n2,90\n")
    pid = client.post("/pipelines", json={"name": "compile-doc", "document": None}).json()["id"]
    saved = _pipeline_with_predicate(pid, csv, "val > 80")
    resp = client.put(f"/pipelines/{pid}", json={"document": saved, "expectedEtag": 1})
    assert resp.status_code == 200

    client.post(
        f"/pipelines/{pid}/compile",
        params={"terminal": "n_f"},
        json={"document": _pipeline_with_predicate(pid, csv, "val > 20")},
    )
    stored = client.get(f"/pipelines/{pid}").json()["document"]
    assert stored["nodes"][0]["params"]["predicate"] == "val > 80"


def test_allow_database_permits_real_db_exports_but_never_the_catalog(tmp_db: Path) -> None:
    """`export_to_db` legitimately creates SQLite/DuckDB files.

    `allow_database=True` lifts the blanket database-file rule for that step
    while keeping the two things that must never be writable: DIG's own
    catalog, and the input roots. Without the carve-out the guard would have
    broken every legitimate database export.
    """
    ok = data_dir() / "outputs" / "run1" / "results.db"
    assert assert_write_target_safe(str(ok), allow_database=True) == ok.resolve()

    with pytest.raises(ValueError, match="catalog database"):
        assert_write_target_safe(str(data_dir() / "dig.sqlite"), allow_database=True)
    with pytest.raises(ValueError, match="source data"):
        assert_write_target_safe(
            str(data_dir() / "uploads" / "x.db"), allow_database=True
        )

"""Canary tests for the backend two-pass preview (M7).

The `/pipelines/{id}/preview` route runs two statements on the same DuckDB
connection: a rows page and a projection-pruned `count(*)`, both wrapped as
``SELECT ... FROM (<compiled sql> LIMIT <sample_rows>) AS __preview``. Two
properties have to hold and are easy to silently break:

1. The count pass sees the SAME sampled subquery as the rows pass, so a
   fully-materialised small pipeline reports `rowCount == N` (not the
   `preview_limit`, not a de-duplicated/partial count).
2. A top-level ``ORDER BY`` in the compiled SQL survives the LIMIT wrapper.
   DuckDB is free to drop ordering it deems non-observable, so the sort node's
   ordering must still be reflected in the returned rows.

These are asserted against a tiny CSV with a known `id` column so the exact
row order is checkable.
"""

from __future__ import annotations

from pathlib import Path


def _write_id_csv(tmp_path: Path, n: int) -> Path:
    """Write a CSV with a single `id` column holding 1..n (ascending)."""
    csv = tmp_path / "ids.csv"
    lines = ["id"] + [str(i) for i in range(1, n + 1)]
    csv.write_text("\n".join(lines) + "\n")
    return csv


def _create_pipeline_with_doc(client, csv_path: Path, nodes: list, output_ref: str) -> str:
    """POST a pipeline, then PUT a document wiring the CSV → nodes → one output.

    Returns the pipeline id. Uses the etag returned from the create to guard
    the first save (the initial doc-less pipeline has etag 1).
    """
    r = client.post("/pipelines", json={"name": "preview-canary", "document": None})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    doc = {
        "schemaVersion": 1,
        "id": pid,
        "name": "preview-canary",
        "datasets": [
            {"id": "ds", "connector": "csv", "uri": f"file://{csv_path}"}
        ],
        "nodes": nodes,
        "outputs": [{"id": "o", "name": "out", "from": {"ref": output_ref}}],
    }
    r = client.put(f"/pipelines/{pid}", json={"document": doc, "expectedEtag": 1})
    assert r.status_code == 200, r.text
    return pid


def test_preview_sort_desc_order_and_count_survive_limit_wrapper(client, tmp_path) -> None:
    """sort_rows(id DESC) → preview must return all N rows in descending id order.

    Guards: (a) `rowCount == N` — the second count pass sees the same sampled
    subquery as the rows pass; (b) the top-level ORDER BY survives the
    ``SELECT * FROM (<sql> LIMIT n) AS __preview`` wrapper.
    """
    n = 7
    csv = _write_id_csv(tmp_path, n)
    nodes = [
        {
            "id": "n_sort",
            "step": "sort_rows",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "ds"}},
            "params": {"by": [{"column": "id", "direction": "desc"}]},
        }
    ]
    pid = _create_pipeline_with_doc(client, csv, nodes, output_ref="n_sort")

    r = client.post(f"/pipelines/{pid}/preview", params={"terminal": "n_sort"})
    assert r.status_code == 200, r.text
    body = r.json()

    # Count pass matches the full sample.
    assert body["rowCount"] == n, body

    # ORDER BY survived the LIMIT wrapper: ids must be N, N-1, ..., 1.
    ids = [int(row["id"]) for row in body["rows"]]
    assert ids == list(range(n, 0, -1)), ids


def test_preview_filter_then_sort_reduces_count(client, tmp_path) -> None:
    """filter_rows(id <= K) → sort_rows(id DESC): rowCount must be K, ordered.

    Guards that the count pass reflects the row-reducing filter (not the raw
    source size) and that ordering still holds after the reduction.
    """
    n = 7
    k = 4
    csv = _write_id_csv(tmp_path, n)
    nodes = [
        {
            "id": "n_filter",
            "step": "filter_rows",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "ds"}},
            "params": {"predicate": f"id <= {k}"},
        },
        {
            "id": "n_sort",
            "step": "sort_rows",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "n_filter"}},
            "params": {"by": [{"column": "id", "direction": "desc"}]},
        },
    ]
    pid = _create_pipeline_with_doc(client, csv, nodes, output_ref="n_sort")

    r = client.post(f"/pipelines/{pid}/preview", params={"terminal": "n_sort"})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["rowCount"] == k, body
    ids = [int(row["id"]) for row in body["rows"]]
    assert ids == list(range(k, 0, -1)), ids

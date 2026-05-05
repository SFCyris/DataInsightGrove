"""Smoke tests for the v0.6 routes (diff, history, lineage, templates).

These existed with zero coverage at the v0.6 baseline; this file is the
seed for that gap. Each test is self-contained — creates a pipeline,
exercises a single endpoint, asserts the load-bearing fields.
"""

from __future__ import annotations

import pytest


def _new_pipeline(client, name: str = "T") -> str:
    """Helper: POST a minimal pipeline; return its id."""
    r = client.post(
        "/pipelines",
        json={"name": name, "document": None},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_history_diff_round_trip(client) -> None:
    """Save a pipeline twice with a real change; diff should show the change."""
    pid = _new_pipeline(client, "diff-target")
    # First save: add a dataset
    doc1 = {
        "schemaVersion": 1, "id": pid, "name": "diff-target",
        "datasets": [{"id": "ds1", "connector": "csv", "uri": "file:///tmp/x.csv"}],
        "nodes": [], "outputs": [],
    }
    r = client.put(f"/pipelines/{pid}", json={"document": doc1, "expectedEtag": 1})
    assert r.status_code == 200, r.text
    etag = r.json()["etag"]

    # Second save: add a node
    doc2 = {
        **doc1,
        "nodes": [{
            "id": "n1", "step": "filter_rows", "stepVersion": "0.1.0",
            "inputs": {"in": {"ref": "ds1"}}, "outputs": ["out"],
            "params": {"predicate": "true"},
        }],
    }
    r = client.put(f"/pipelines/{pid}", json={"document": doc2, "expectedEtag": etag})
    assert r.status_code == 200, r.text

    # History should have both snapshots.
    h = client.get(f"/pipelines/{pid}/history").json()
    assert len(h) >= 2

    # Diff `previous` → `current` should report the added node.
    d = client.post(
        f"/pipelines/{pid}/diff",
        json={"fromRef": "previous", "toRef": "current"},
    ).json()
    kinds = {s["kind"] for s in d["steps"]}
    assert "added" in kinds


def test_history_dedup_no_op_save(client) -> None:
    """Saving the same document shouldn't write a second snapshot."""
    pid = _new_pipeline(client, "dedup")
    # Initial empty pipeline gets one "import" snapshot. PUT-ing the same
    # doc should be deduped by hash.
    doc = client.get(f"/pipelines/{pid}").json()["document"]
    client.put(f"/pipelines/{pid}", json={"document": doc, "expectedEtag": 1})
    h1 = client.get(f"/pipelines/{pid}/history").json()
    client.put(f"/pipelines/{pid}", json={"document": doc, "expectedEtag": 2})
    h2 = client.get(f"/pipelines/{pid}/history").json()
    # Hash dedup means no new snapshot was added on the second save.
    assert len(h2) == len(h1)


def test_run_ref_404s_unknown_run(client) -> None:
    """The `run:<id>` ref must 404 when the run-id doesn't match a snapshot
    (the prior implementation silently fell back to the latest snapshot)."""
    pid = _new_pipeline(client, "run-ref")
    r = client.post(
        f"/pipelines/{pid}/diff",
        json={"fromRef": "current", "toRef": "run:00000000000000000000000000"},
    )
    assert r.status_code == 404


def test_template_create_strip_secrets(client) -> None:
    """Publishing a template should redact `password=*` URI components."""
    pid = _new_pipeline(client, "with-secret")
    doc = {
        "schemaVersion": 1, "id": pid, "name": "with-secret",
        "datasets": [{
            "id": "ds1", "connector": "postgres",
            "uri": "postgres://user:hunter2@host/db",
        }],
        "nodes": [], "outputs": [],
    }
    client.put(f"/pipelines/{pid}", json={"document": doc, "expectedEtag": 1})

    r = client.post("/templates", json={"pipelineId": pid, "title": "secret-template"})
    assert r.status_code == 201, r.text
    slug = r.json()["slug"]
    detail = client.get(f"/templates/{slug}").json()
    saved_uri = detail["document"]["datasets"][0]["uri"]
    assert "hunter2" not in saved_uri
    assert "__redacted__" in saved_uri


def test_template_listing_does_not_expose_private(client) -> None:
    """Private templates must not appear in the public list."""
    pid = _new_pipeline(client, "private-template")
    client.put(
        f"/pipelines/{pid}",
        json={
            "document": {
                "schemaVersion": 1, "id": pid, "name": "private-template",
                "datasets": [], "nodes": [], "outputs": [],
            },
            "expectedEtag": 1,
        },
    )
    client.post(
        "/templates",
        json={"pipelineId": pid, "title": "should-be-private", "visibility": "private"},
    )
    listing = client.get("/templates").json()
    assert all(t["title"] != "should-be-private" for t in listing)


@pytest.mark.parametrize("slug", [
    "../../../../etc/hosts",
    "../../README",
])
def test_template_clone_rejects_traversal(client, slug: str) -> None:
    """Path-traversal slugs must 400 instead of attempting a path read.

    `..` and `with/slash` get normalized by Starlette routing into
    different URL patterns and never reach our handler — those aren't
    interesting to test here, only the slug-shaped values.
    """
    r = client.post(f"/pipelines/templates/{slug}")
    # 400 = rejected by validation; 404 = whitelisted-but-not-bundled.
    # The crucial part is we don't 500 with a path-error response body.
    assert r.status_code in (400, 404)

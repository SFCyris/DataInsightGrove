"""Route-level tests for /packs/upload — body cap + staging flow.

Covers the two size gates that guard the pack-upload path:

  * The per-route 64 MiB body cap in `BodySizeLimitMiddleware`
    (`_ROUTE_MAX_BODY_BYTES["/packs/upload"]`), which admits payloads a
    32 MiB-capped route rejects. We prove isolation WITHOUT a 64 MiB
    payload: a ~40 MiB body is admitted at /packs/upload (surfacing a
    400 PackError from content validation, not a 413) yet 413s at a
    default-capped route.
  * The pack-module `_MAX_ARCHIVE_BYTES` ceiling enforced by the upload
    handler's own read loop.

Plus a happy-path stage of a minimal valid `.dpack`.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from dig.plugins import packs as pack_mod


# ── Fixtures / helpers ─────────────────────────────────────────────


def _minimal_dpack(pack_id: str = "demopack", version: str = "1.0.0") -> bytes:
    """Build the smallest archive `stage_pack` accepts.

    A pack with no declared steps needs only `<id>/pack.json`: the
    steps/ cross-check is skipped when `steps` is absent, so this is the
    minimal valid layout.
    """
    manifest = {
        "id": pack_id,
        "version": version,
        "label": "🧪 Demo Pack",
        "description": "A minimal pack used by the upload tests.",
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{pack_id}/pack.json", json.dumps(manifest))
    return out.getvalue()


# ── Body-cap isolation ─────────────────────────────────────────────


def test_upload_admits_40mib_body_that_default_route_rejects(client) -> None:
    """~40 MiB proves the per-route override without a 64 MiB payload.

    The body sits above the 32 MiB global default but below both the
    64 MiB /packs/upload cap and the 50 MiB pack ceiling, so:
      * /packs/upload admits it — the middleware lets it through and the
        handler reaches `stage_pack`, which 400s because the bytes are
        not a valid zip. NOT 413 is the assertion that matters.
      * a default-capped route (PUT /pipelines/{id}) 413s on the same
        body at the Content-Length pre-check, before routing.
    """
    payload = b"\x00" * (40 * 1024 * 1024)  # 40 MiB, between 32 and 50

    # Admitted by the 64 MiB /packs/upload cap → rejected downstream as
    # bad content, not by the body-size middleware.
    up = client.post(
        "/packs/upload",
        files={"file": ("dummy.dpack", payload, "application/octet-stream")},
    )
    assert up.status_code != 413, up.text
    assert up.status_code == 400, up.text
    assert "zip" in up.text.lower()

    # Same body to a route that only has the 32 MiB global cap → 413.
    put = client.put("/pipelines/does-not-matter", content=payload)
    assert put.status_code == 413, put.text
    assert "too large" in put.text.lower()


# ── Pack-module archive ceiling ────────────────────────────────────


def test_upload_rejects_when_archive_exceeds_max_bytes(
    client, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A small upload 400s once `_MAX_ARCHIVE_BYTES` is lowered under it.

    The handler reads the spool back and enforces the pack ceiling so an
    archive in the (pack-cap, body-cap) gap gets a clear 400 instead of
    the middleware's generic 413. Drive that path by shrinking the cap
    to 1 KiB and sending ~2 KiB.
    """
    monkeypatch.setattr(pack_mod, "_MAX_ARCHIVE_BYTES", 1024)
    payload = b"\x00" * 2048

    resp = client.post(
        "/packs/upload",
        files={"file": ("small.dpack", payload, "application/octet-stream")},
    )
    assert resp.status_code == 400, resp.text
    assert "archive too large" in resp.text.lower()


# ── Happy-path staging ─────────────────────────────────────────────


def test_upload_stages_minimal_valid_dpack(
    client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A minimal valid .dpack stages and returns its manifest fields.

    `stage_pack` materialises the archive under `PENDING_PACKS_DIR`; we
    redirect that at a tmp dir so the test never writes into the repo's
    plugins/_pending tree.
    """
    monkeypatch.setattr(pack_mod, "PENDING_PACKS_DIR", tmp_path / "_pending")

    dpack = _minimal_dpack(pack_id="demopack", version="1.0.0")
    resp = client.post(
        "/packs/upload",
        files={"file": ("demopack-1.0.0.dpack", dpack, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pack_id"] == "demopack"
    assert body["version"] == "1.0.0"
    assert body["label"] == "🧪 Demo Pack"
    assert body["steps"] == []
    assert body["connectors"] == []
    # Checksum is computed over the payload (pack.json excluded) — a
    # steps-less pack hashes to the empty-content sha256.
    assert body["computed_checksum"].startswith("sha256:")
    # The staged dir landed under the redirected pending root.
    assert (tmp_path / "_pending" / "demopack-1.0.0" / "pack.json").exists()

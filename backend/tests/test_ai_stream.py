"""Coverage for the SSE pipeline-explain endpoint.

`POST /ai/explain-pipeline/{id}/stream` (dig/api/ai.py:explain_stream) had
zero tests. It streams Server-Sent Events: a leading `data: {"model": ...}`
frame, one `data: {"delta": ...}` per generated token, and a trailing
`data: [DONE]`. Provider errors that surface after the stream has opened
arrive as `data: {"error": ...}` while the HTTP status stays 200 (already
committed); config / not-found errors raise BEFORE streaming starts so they
keep their proper 400 / 404 status.

The provider call (`chat_stream`) and config load (`load_config`) are both
monkeypatched so the tests never touch a real AI provider. A drift guard
asserts the streaming path feeds `chat_stream` the exact messages the shared
`build_explain_messages` builder produces for the same doc + catalog — the
two explain paths must not diverge.
"""

from __future__ import annotations

import json

import pytest

from dig.ai.client import AiConfig, AiError
from dig.ai.features.explain import build_explain_messages
from dig.engine.registry import steps as steps_registry


def _new_pipeline(client, name: str = "explain-target") -> str:
    """POST a minimal pipeline; return its id."""
    r = client.post("/pipelines", json={"name": name, "document": None})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _put_doc(client, pid: str) -> dict:
    """Save a real document so the explain prompt has content to describe.
    Returns the saved document (what the endpoint reads back)."""
    doc = {
        "schemaVersion": 1, "id": pid, "name": "explain-target",
        "datasets": [{"id": "ds1", "connector": "csv", "uri": "file:///tmp/x.csv"}],
        "nodes": [{
            "id": "n1", "step": "filter_rows", "stepVersion": "0.1.0",
            "inputs": {"in": {"ref": "ds1"}}, "outputs": ["out"],
            "params": {"predicate": "true"},
        }],
        "outputs": [],
    }
    r = client.put(f"/pipelines/{pid}", json={"document": doc, "expectedEtag": 1})
    assert r.status_code == 200, r.text
    return doc


def _enabled_cfg() -> AiConfig:
    return AiConfig(
        enabled=True,
        provider="local",
        endpoint="http://localhost:11434/v1",
        model="test-model",
        api_key=None,
    )


def _patch_config(monkeypatch, cfg: AiConfig) -> None:
    """Replace dig.api.ai.load_config with an async fn returning `cfg`."""
    async def _fake_load_config(_session) -> AiConfig:
        return cfg
    monkeypatch.setattr("dig.api.ai.load_config", _fake_load_config)


def _patch_stream(monkeypatch, tokens, *, raise_after=None, captured=None):
    """Replace dig.api.ai.client_chat_stream with a controlled async
    generator. Yields each of `tokens` in order; if `raise_after` is set,
    raises AiError(raise_after) once the tokens are exhausted. When
    `captured` is a dict, records the messages/kwargs the endpoint passed."""
    async def _fake_chat_stream(cfg, messages, *, temperature=None, max_tokens=None, **_kw):
        if captured is not None:
            captured["messages"] = messages
            captured["temperature"] = temperature
            captured["max_tokens"] = max_tokens
        for tok in tokens:
            yield tok
        if raise_after is not None:
            raise AiError(raise_after)

    monkeypatch.setattr("dig.api.ai.client_chat_stream", _fake_chat_stream)


def _parse_sse(text: str) -> list[str]:
    """Return the ordered list of `data:` payloads from an SSE body."""
    return [
        line[len("data: "):]
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def test_stream_disabled_returns_400_not_event_stream(client, monkeypatch) -> None:
    """AI disabled (the default) → 400 before the stream opens, and the
    response is NOT an event stream."""
    pid = _new_pipeline(client)
    cfg = _enabled_cfg()
    cfg.enabled = False
    _patch_config(monkeypatch, cfg)
    # chat_stream must never be reached; a booby-trapped patch proves it.
    _patch_stream(monkeypatch, tokens=["nope"])

    r = client.post(f"/ai/explain-pipeline/{pid}/stream")
    assert r.status_code == 400, r.text
    assert "text/event-stream" not in r.headers.get("content-type", "")


def test_stream_unknown_pipeline_404(client, monkeypatch) -> None:
    """Unknown pipeline id → 404 before streaming starts."""
    _patch_config(monkeypatch, _enabled_cfg())
    _patch_stream(monkeypatch, tokens=["nope"])

    r = client.post("/ai/explain-pipeline/does-not-exist/stream")
    assert r.status_code == 404, r.text


def test_stream_happy_path(client, monkeypatch) -> None:
    """Enabled + known pipeline → 200 text/event-stream: a model frame,
    one delta per token in order, terminated by [DONE]."""
    pid = _new_pipeline(client)
    _put_doc(client, pid)
    _patch_config(monkeypatch, _enabled_cfg())
    tokens = ["This ", "pipeline ", "filters ", "rows."]
    _patch_stream(monkeypatch, tokens=tokens)

    with client.stream("POST", f"/ai/explain-pipeline/{pid}/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache, no-transform"
        body = "".join(r.iter_text())

    payloads = _parse_sse(body)
    # First frame carries the model, last is the terminator.
    assert json.loads(payloads[0]) == {"model": "test-model"}
    assert payloads[-1] == "[DONE]"

    deltas = [json.loads(p)["delta"] for p in payloads[1:-1]]
    assert deltas == tokens  # one delta per token, in order
    assert '"model": "test-model"' in body


def test_stream_error_mid_stream(client, monkeypatch) -> None:
    """Generator yields a token then raises AiError → the delta is emitted,
    then an error frame, then [DONE]; HTTP status stays 200 (committed)."""
    pid = _new_pipeline(client)
    _put_doc(client, pid)
    _patch_config(monkeypatch, _enabled_cfg())
    _patch_stream(
        monkeypatch, tokens=["partial "], raise_after="upstream exploded",
    )

    with client.stream("POST", f"/ai/explain-pipeline/{pid}/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())

    payloads = _parse_sse(body)
    assert json.loads(payloads[0]) == {"model": "test-model"}
    assert json.loads(payloads[1]) == {"delta": "partial "}
    assert json.loads(payloads[2]) == {"error": "upstream exploded"}
    assert payloads[-1] == "[DONE]"


def test_stream_prompt_matches_shared_builder(client, monkeypatch) -> None:
    """L4 drift guard: the messages the streaming path feeds `chat_stream`
    must equal `build_explain_messages(doc, catalog)` for the same inputs —
    the streaming + non-streaming explain paths share one prompt builder."""
    pid = _new_pipeline(client)
    doc = _put_doc(client, pid)
    _patch_config(monkeypatch, _enabled_cfg())
    captured: dict = {}
    _patch_stream(monkeypatch, tokens=["x"], captured=captured)

    with client.stream("POST", f"/ai/explain-pipeline/{pid}/stream") as r:
        assert r.status_code == 200
        "".join(r.iter_text())  # drain so the generator fully runs

    catalog = [s.manifest for s in steps_registry().all()]
    expected = build_explain_messages(doc, catalog)
    assert captured["messages"] == expected

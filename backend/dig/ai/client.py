"""OpenAI-compatible chat-completions client.

One small HTTP client that talks to every provider in the field — Ollama,
llama.cpp, vLLM, OpenAI, Anthropic (via /v1/messages compat), Groq,
OpenRouter, Together, LiteLLM. They all accept the same JSON shape:

    POST {endpoint}/chat/completions
    Authorization: Bearer {api_key}        # only when set
    {
      "model": "...",
      "messages": [{"role": "system|user|assistant", "content": "..."}],
      "temperature": 0.0,
      "max_tokens": 4096,
      "stream": false
    }

Returns:
    {"choices": [{"message": {"content": "..."}}], "usage": {...}}

We use httpx (already a transitive dep via FastAPI/starlette) so no new
package needed. Streaming is supported but not required by current
features — they're all "one prompt → one response" shape.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Default timeout — local Ollama on a laptop can be slow to first-token
# on a cold model. 120s covers cold-start + a typical generation; users
# with sluggish hardware can override per-call.
_DEFAULT_TIMEOUT_S = 120.0


class AiError(Exception):
    """Raised when the AI provider returns an error or is unreachable."""


@dataclass
class AiConfig:
    """Resolved AI settings — read from the key/value settings table."""
    enabled: bool
    provider: str        # "local" | "openai_compat" | "disabled"
    endpoint: str        # e.g. http://localhost:11434/v1
    model: str           # e.g. gemma4:e4b
    api_key: str | None  # masked on read in the settings API
    max_tokens: int = 4096
    temperature: float = 0.0

    def __repr__(self) -> str:
        # Redact api_key in any logging / repr output. Without this an
        # `f"{cfg!r}"` in a log line would leak the live key.
        masked = "***set***" if self.api_key else None
        return (
            f"AiConfig(enabled={self.enabled}, provider={self.provider!r}, "
            f"endpoint={self.endpoint!r}, model={self.model!r}, api_key={masked}, "
            f"max_tokens={self.max_tokens}, temperature={self.temperature})"
        )


@dataclass
class AiResponse:
    """One chat completion. `text` is the assistant message content;
    `usage` carries token counts when the provider reports them
    (Ollama doesn't always)."""
    text: str
    model: str
    usage: dict[str, int] | None = None


def _normalize_endpoint(endpoint: str) -> str:
    """Strip trailing slash and ensure /v1 suffix where the user dropped it.

    Ollama's compat URL is http://localhost:11434/v1; many users paste
    just http://localhost:11434. We tolerate both.

    Pen-tester round-2 finding: previously this accepted any scheme,
    so `file:///etc/passwd` or `gopher://...` reached httpx (which would
    block file:// today, but a future transport pivot is one version
    bump from RCE). Restrict to http(s) up front.

    Round-3 follow-up: validate scheme + host BEFORE any string
    manipulation. The previous order (rstrip → parse → check) ran
    rstrip/append-`/v1` on inputs that were about to be rejected, which
    made the rejected error path return a value that didn't match what
    the caller passed in — confusing in logs and brittle to refactor.
    """
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise AiError("AI endpoint must be a non-empty string")
    from urllib.parse import urlparse as _urlparse
    parsed = _urlparse(endpoint.strip())
    if parsed.scheme not in ("http", "https"):
        raise AiError(
            f"AI endpoint scheme must be http or https; got {parsed.scheme!r}",
        )
    if not parsed.netloc:
        raise AiError(f"AI endpoint must include a host; got {endpoint!r}")
    e = endpoint.strip().rstrip("/")
    if not e.endswith("/v1"):
        # Best-effort: if the user pasted a bare host, append /v1.
        # OpenAI proper (api.openai.com/v1) and Anthropic compat
        # (api.anthropic.com/v1) both follow the convention.
        e = e + "/v1"
    return e


async def chat(
    cfg: AiConfig,
    messages: list[dict[str, str]],
    *,
    response_format: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> AiResponse:
    """Send a single chat completion and return the assistant message.

    Args:
      cfg: resolved provider settings (load via dig.ai.config.load_config)
      messages: standard chat shape — list of {role, content}
      response_format: pass "json_object" for providers that support
        structured output enforcement (OpenAI, recent Ollama). Falls
        back gracefully for providers that don't.
      temperature, max_tokens: per-call overrides; default to cfg values
      timeout_s: HTTP timeout

    Raises:
      AiError if the provider returns non-200, malformed JSON, or no choices.
    """
    if not cfg.enabled or cfg.provider == "disabled":
        raise AiError("AI is disabled — enable it in Settings → AI")

    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature if temperature is not None else cfg.temperature,
        "max_tokens": max_tokens if max_tokens is not None else cfg.max_tokens,
        "stream": False,
    }
    if response_format == "json_object":
        # OpenAI + Ollama recent versions accept this. Providers that
        # don't will simply ignore the field — generation still works,
        # the caller must be more forgiving when parsing.
        payload["response_format"] = {"type": "json_object"}

    url = _normalize_endpoint(cfg.endpoint) + "/chat/completions"
    log.debug("AI POST %s model=%s", url, cfg.model)

    # Pen-tester round-2: same SSRF defence-in-depth as generate_connector
    # (which got it right): pre-call URL validation. Without this, an
    # operator (or anyone with settings-write) who sets
    # ai_endpoint=http://169.254.169.254/v1 can harvest cloud instance
    # metadata via /ai/test-connection.
    try:
        from connectors.rest_api.connector import _assert_url_safe
        _assert_url_safe(url)
    except (ValueError, ImportError) as e:
        raise AiError(f"AI endpoint URL rejected: {e}") from e

    try:
        # follow_redirects=False — pre-call URL validation (above) is a
        # TOCTOU pre-check; a 302 to an internal address would silently
        # bypass it. Pin the default so an httpx version flip doesn't
        # reopen the SSRF gate.
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False) as client:
            r = await client.post(url, json=payload, headers=headers)
            # Defence-in-depth against DNS rebinding TOCTOU — see the REST
            # connector.
            try:
                from connectors.rest_api.connector import _assert_response_peer_safe
                _assert_response_peer_safe(r)
            except (RuntimeError, ImportError) as e:
                raise AiError(f"AI endpoint rejected post-connect: {e}") from e
    except httpx.TimeoutException as e:
        raise AiError(f"AI request timed out after {timeout_s}s — model may be cold-loading") from e
    except httpx.RequestError as e:
        raise AiError(
            f"AI provider unreachable at {url}: {e}. "
            "Check Settings → AI · Test connection.",
        ) from e

    if r.status_code != 200:
        # When the request carried an Authorization header, redact the
        # response body — some misbehaving upstreams echo headers back
        # in error pages, which would leak the bearer token to the user
        # via the 502 surface.
        if cfg.api_key:
            raise AiError(f"AI provider returned HTTP {r.status_code}")
        raise AiError(
            f"AI provider returned {r.status_code}: {r.text[:300]}",
        )

    try:
        body = r.json()
    except ValueError as e:
        raise AiError(f"AI provider returned non-JSON: {r.text[:300]}") from e

    choices = body.get("choices") or []
    if not choices:
        raise AiError(f"AI provider returned no choices: {body}")

    msg = choices[0].get("message") or {}
    text = msg.get("content") or ""
    if not text.strip():
        raise AiError("AI provider returned an empty message")

    return AiResponse(
        text=text,
        model=body.get("model") or cfg.model,
        usage=body.get("usage"),
    )


async def list_models(cfg: AiConfig, *, timeout_s: float = 10.0) -> list[str]:
    """Fetch the list of available models from the configured endpoint.

    Calls GET {endpoint}/models — the standard OpenAI list-models shape
    that Ollama, llama.cpp, vLLM, Anthropic-compat, OpenAI, Groq,
    OpenRouter, Together all implement. Response shape:
        {"object": "list", "data": [{"id": "model-name", ...}, ...]}

    Returns model IDs sorted alphabetically. On any error (network,
    auth, malformed response, missing endpoint) returns an EMPTY LIST —
    callers should treat empty as "couldn't fetch" and fall back to
    the free-text input. Never raises.
    """
    if cfg.provider == "disabled" or not (cfg.endpoint or "").strip():
        return []

    headers = {"Accept": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    url = _normalize_endpoint(cfg.endpoint) + "/models"
    # Same SSRF gate as `chat()` — pre-call URL safety check. list_models
    # is "never raises", so on rejection just return empty + debug-log.
    try:
        from connectors.rest_api.connector import _assert_url_safe
        _assert_url_safe(url)
    except (ValueError, ImportError) as e:
        log.debug("AI list_models: URL rejected (%s)", e)
        return []
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False) as client:
            r = await client.get(url, headers=headers)
    except (httpx.RequestError, httpx.TimeoutException) as e:
        log.debug("AI list_models: %s unreachable (%s)", url, e)
        return []
    if r.status_code != 200:
        log.debug("AI list_models: HTTP %d from %s", r.status_code, url)
        return []
    try:
        body = r.json()
    except ValueError:
        log.debug("AI list_models: non-JSON response from %s", url)
        return []

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, dict):
            mid = item.get("id")
            if isinstance(mid, str) and mid:
                out.append(mid)
        elif isinstance(item, str):
            out.append(item)
    return sorted(set(out))


async def probe(cfg: AiConfig, *, timeout_s: float = 10.0) -> dict[str, Any]:
    """Send a tiny ping to verify the provider is reachable and the
    model exists. Returns a small status dict for the Test Connection UI.

    Doesn't raise — failures land in the returned dict so the UI can
    show a friendly error.
    """
    if cfg.provider == "disabled" or not cfg.enabled:
        return {"ok": False, "error": "AI is disabled"}
    try:
        resp = await chat(
            cfg,
            messages=[
                {"role": "system", "content": "You are a healthcheck. Reply with the single word 'pong'."},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=8,
            temperature=0.0,
            timeout_s=timeout_s,
        )
        return {
            "ok": True,
            "model": resp.model,
            "reply": resp.text.strip()[:40],
            "usage": resp.usage,
        }
    except AiError as e:
        return {"ok": False, "error": str(e)}

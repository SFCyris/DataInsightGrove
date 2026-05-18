"""Outbound webhook dispatch on run completion.

Fires when a run reaches a terminal status (succeeded / failed). The list of
webhooks lives on the pipeline document (`pipeline.webhooks`); each entry has
a URL, an `on` selector (always / succeeded / failed), optional shared secret
for HMAC signing, and optional extra headers.

Why on the pipeline (not on the run): webhooks describe a long-lived
integration ("notify Slack whenever this pipeline runs"), so they belong with
the pipeline definition rather than per-invocation. Per-invocation needs can
be served via the API client posting to `/runs/{id}` directly.

Failure handling: each POST has a short timeout and a single retry. Webhook
delivery failures are logged but never propagate — a misconfigured receiver
must not bury a successful run's status.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from dig.engine.pipeline import Pipeline, Webhook

log = logging.getLogger(__name__)


# Conservative defaults. The whole job manager is single-process; we don't
# want a slow webhook receiver to back up the in-flight task pool.
_TIMEOUT_S = 10.0
_RETRY_DELAY_S = 2.0


def _should_fire(hook: Webhook, status: str) -> bool:
    # `triggered` webhooks never fire from the auto-dispatch on a run's
    # terminal status — they're invoked explicitly by the `webhook_trigger`
    # step inside a pipeline (or by other code that calls dispatch_one()).
    if hook.on == "triggered":
        return False
    if hook.on == "always":
        # Round-9 fix: cancelled is a terminal status that used to be
        # silently skipped here, so an "always" webhook never fired on
        # user-cancels. Now it's part of the terminal set.
        return status in ("succeeded", "failed", "cancelled")
    return hook.on == status


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def _post_one(client: httpx.AsyncClient, hook: Webhook, body: bytes) -> None:
    # Pipeline docs (and the GlobalWebhook table) are user-supplied — without
    # a private-IP check, an imported template could fire webhooks at e.g.
    # http://169.254.169.254/latest/meta-data/ to harvest cloud-instance
    # metadata, or at http://localhost:11434/ to poke local services. Same
    # check the REST connector uses; same DIG_REST_ALLOW_PRIVATE escape hatch.
    try:
        from connectors.rest_api.connector import _assert_url_safe
        _assert_url_safe(hook.url)
    except ValueError as e:
        log.warning("webhook %s rejected: %s", hook.url, e)
        return

    # Pen-tester round-3: hook.headers came from a user-supplied pipeline
    # document and was spread into the outbound request without any check.
    # A value containing "\r\n" would splice an extra header (or even a
    # second request body) into the wire format. Reuse the REST connector's
    # validator so both surfaces share one allow-list.
    try:
        from connectors.rest_api.connector import _validate_header_pair
    except ImportError:
        _validate_header_pair = None  # type: ignore[assignment]
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DataInsightGrove-Webhook/1.0",
    }
    for k, v in hook.headers.items():
        if _validate_header_pair is not None:
            try:
                n, val = _validate_header_pair(str(k), str(v))
            except ValueError as e:
                log.warning("webhook %s rejected header %r: %s", hook.url, k, e)
                return
            headers[n] = val
        else:
            headers[str(k)] = str(v)
    if hook.secret:
        headers["X-DIG-Signature"] = _sign(body, hook.secret)

    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            resp = await client.post(hook.url, content=body, headers=headers, timeout=_TIMEOUT_S)
            # Defense-in-depth against DNS rebinding: validate the actual
            # TCP peer the connection landed on. Same shape as the REST
            # connector's ``_assert_response_peer_safe`` — without this,
            # ``_assert_url_safe`` (above) is a TOCTOU check that a
            # malicious DNS server can race by returning a public IP for
            # the first lookup and ``127.0.0.1`` for the second. Round-3
            # pen-tester finding.
            try:
                from connectors.rest_api.connector import _assert_response_peer_safe
                _assert_response_peer_safe(resp)
            except RuntimeError as e:
                last_err = e
                # Don't retry — the receiver is mis-resolved, retrying
                # gives them a second exfiltration attempt.
                break
            # Treat 2xx as success. Receivers commonly return 200/201/202/204.
            if 200 <= resp.status_code < 300:
                log.info("webhook %s → %s (attempt %d)", hook.url, resp.status_code, attempt)
                return
            # Round-9 fix: only include response body in the logged
            # error when the hook has NO secret + NO custom headers.
            # An attacker-controlled receiver can echo our request
            # headers (including the HMAC signature or operator-set
            # tokens) back in the error body and leak them through
            # this log line.
            if hook.secret or hook.headers:
                last_err = RuntimeError(f"HTTP {resp.status_code} (body redacted — hook uses secrets)")
            else:
                last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            last_err = e
        if attempt == 1:
            await asyncio.sleep(_RETRY_DELAY_S)
    # Both attempts exhausted — log and move on. We never raise into the
    # caller; a broken webhook can't bury the run status.
    log.warning("webhook %s failed after 2 attempts: %s", hook.url, last_err)


async def dispatch(pipeline: Pipeline, payload: dict[str, Any]) -> None:
    """Fire all matching webhooks for the given run payload, in parallel.

    `payload` is the JSON-encodable run summary (see jobs/manager.py for the
    exact fields). `pipeline.webhooks` is the source of receivers.
    """
    status = str(payload.get("status", ""))
    receivers = [h for h in pipeline.webhooks if _should_fire(h, status)]
    if not receivers:
        return
    body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    # follow_redirects=False is critical defence-in-depth: _assert_url_safe()
    # is a TOCTOU pre-check on the original URL; a 302 to an internal address
    # would silently bypass it. Pin explicitly so an httpx default change
    # doesn't quietly open the SSRF gate.
    async with httpx.AsyncClient(follow_redirects=False) as client:
        await asyncio.gather(
            *(_post_one(client, h, body) for h in receivers),
            return_exceptions=False,
        )


async def dispatch_one(hook: Webhook, payload: dict[str, Any]) -> None:
    """Fire a single webhook with the given payload.

    Used by the in-pipeline `webhook_trigger` step. Bypasses the
    `_should_fire` guard — if you call this you've already decided to
    fire — but reuses the same retry / timeout / signing path so behavior
    matches the auto-dispatch case exactly.
    """
    body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    # Pen-tester round-2: this single-fire path missed the
    # `follow_redirects=False` pin that the multi-fire `dispatch` got in
    # round 1. Same SSRF defence-in-depth — without it, a 302 to an
    # internal address would silently bypass `_assert_url_safe`.
    async with httpx.AsyncClient(follow_redirects=False) as client:
        await _post_one(client, hook, body)

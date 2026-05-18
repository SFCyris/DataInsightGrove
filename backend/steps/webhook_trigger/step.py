"""webhook_trigger — fire a global webhook from inside a pipeline.

The user picks a global webhook by label (from the rows in the
`global_webhooks` table managed via Settings → Global webhooks). When this
step executes, it dispatches the webhook with a payload describing the
current run + step + an optional user-supplied JSON blob.

Data passes through unchanged — this is a side-effect step, not a transform.

If the picked label doesn't resolve to a webhook (or `webhookLabel` is
blank), the step logs a warning and passes data through. That's the
"placeholder step" mode the manifest description promises: drop the step
into a flow now, wire it up later once you've created the webhook.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.pipeline import Webhook
from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.jobs.webhooks import dispatch_one

log = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _resolve_webhook(label: str) -> Webhook | None:
    """Look up a global webhook by label. Returns None if not found."""
    from dig.storage.db import SessionLocal
    from dig.storage.models import GlobalWebhook
    from sqlalchemy import select

    async with SessionLocal() as session:
        rows = (await session.execute(
            select(GlobalWebhook).where(GlobalWebhook.label == label)
        )).scalars().all()
    if not rows:
        return None
    if len(rows) > 1:
        log.warning(
            "webhook_trigger: %d webhooks share label '%s'; firing the first",
            len(rows), label,
        )
    row = rows[0]
    if not row.enabled:
        log.info("webhook_trigger: webhook '%s' is disabled — skipping", label)
        return None
    return Webhook(
        url=row.url, on=row.on,  # type: ignore[arg-type]
        secret=row.secret, headers=row.headers or {}, label=row.label,
    )


class WebhookTriggerStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        label = (params.get("webhookLabel") or "").strip()
        extra_raw = (params.get("extraPayload") or "").strip()
        fail_on_error = bool(params.get("failOnError", False))

        if not label:
            log.info("webhook_trigger: webhookLabel is blank — placeholder mode, no fire")
            return PolarsResult(output=df, artifacts=[{
                "kind": "webhook_trigger",
                "fired": False,
                "reason": "no webhook selected",
            }])

        # Parse extra payload (best-effort) — bad JSON is treated as a
        # configuration error since the user opted in by typing something.
        extra: dict[str, Any] = {}
        if extra_raw:
            try:
                extra = json.loads(extra_raw)
                if not isinstance(extra, dict):
                    raise ValueError("extraPayload must be a JSON object, not an array or scalar")
            except (json.JSONDecodeError, ValueError) as e:
                if fail_on_error:
                    raise
                log.warning("webhook_trigger: bad extraPayload JSON (%s) — sending without it", e)
                extra = {}

        run_id = ctx.run_id if ctx else "unknown"
        payload: dict[str, Any] = {
            "event": "step.triggered",
            "runId": run_id,
            # Round-4 QA finding: the auto-dispatch payload includes
            # pipelineId / pipelineName, but the in-pipeline trigger
            # payload only carried runId + stepId. Receivers couldn't
            # correlate a triggered fire back to a pipeline without
            # parsing the runId and querying the DB. Add the two
            # identifiers using the PolarsContext fields wired up for
            # exactly this purpose.
            "pipelineId": ctx.pipeline_id if ctx else None,
            "pipelineName": ctx.pipeline_name if ctx else None,
            "stepId": self.id,
            "stepLabel": self.label,
            "rowCount": df.height,
            "firedAt": _utcnow_iso(),
            **extra,  # user-supplied keys win over defaults — that's the point of "extra"
        }

        # Round-4 QA finding: previously this called ``asyncio.run(_fire())``
        # from inside a worker thread. `_resolve_webhook` opens
        # ``SessionLocal()`` whose aiosqlite engine is bound to the API
        # main event loop — submitting it to a brand-new loop raises
        # ``RuntimeError: ... Future attached to a different loop`` on
        # the first real fire. The fix is the same pattern the
        # subpipeline step uses: hand the coroutine to the API's main
        # loop via ``run_coroutine_threadsafe`` and block here on the
        # concurrent.futures.Future result.
        from dig.jobs.manager import main_loop
        loop = main_loop()
        async def _fire() -> tuple[bool, str | None]:
            hook = await _resolve_webhook(label)
            if hook is None:
                return False, f"no enabled webhook found with label '{label}'"
            try:
                await dispatch_one(hook, payload)
                return True, None
            except Exception as e:  # noqa: BLE001
                return False, f"{type(e).__name__}: {e}"

        if loop is None:
            # No API loop captured yet (e.g. running this step standalone
            # in a test). Fall back to a fresh loop — `_resolve_webhook`
            # opens its OWN session here, so binding is consistent within
            # the call.
            fired, err = asyncio.run(_fire())
        else:
            fut = asyncio.run_coroutine_threadsafe(_fire(), loop)
            fired, err = fut.result(timeout=30)

        artifact: dict[str, Any] = {
            "kind": "webhook_trigger",
            "fired": fired,
            "label": label,
            "stepId": self.id,
        }
        if err:
            artifact["error"] = err
            if fail_on_error:
                raise RuntimeError(f"webhook_trigger: {err}")
            log.warning("webhook_trigger: %s", err)

        return PolarsResult(output=df, artifacts=[artifact])


step = WebhookTriggerStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))

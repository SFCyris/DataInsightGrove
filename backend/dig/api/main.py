from __future__ import annotations

import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from dig import __version__
from dig.api import ai as ai_api
from dig.api import catalog as catalog_api
from dig.api import datasets as datasets_api
from dig.api import notification_rules as notification_rules_api
from dig.api import notifications as notifications_api
from dig.api import packs as packs_api
from dig.api import pipelines as pipelines_api
from dig.api import schedules as schedules_api
from dig.api import search as search_api
from dig.api import settings as settings_api
from dig.api import templates as templates_api
from dig.engine.registry import connectors, steps
from dig.jobs.manager import jobs
from dig.storage.db import init_db

log = logging.getLogger(__name__)


class Health(BaseModel):
    status: str
    version: str
    name: str


# ---- Auth middleware ------------------------------------------------------

def _is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


# Endpoints that bypass the auth check (preflight + health for liveness probes).
_AUTH_BYPASS_PATHS = {"/health"}


# Round-4 DoS #1 — cap incoming request body size. Without this, a
# single PUT /pipelines call with a multi-GB body would buffer in
# memory before pydantic even sees it, OOMing the worker. The cap can
# be raised by ops via DIG_MAX_BODY_BYTES; the default of 32 MiB is
# more than 10× the largest legitimate pipeline doc we've ever seen
# (a 700-node DAG serialised to ~2 MB of JSON).
_DEFAULT_MAX_BODY_BYTES = 32 * 1024 * 1024


def _max_body_bytes() -> int:
    raw = os.environ.get("DIG_MAX_BODY_BYTES")
    if not raw:
        return _DEFAULT_MAX_BODY_BYTES
    try:
        n = int(raw)
        return n if n > 0 else _DEFAULT_MAX_BODY_BYTES
    except ValueError:
        return _DEFAULT_MAX_BODY_BYTES


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose body exceeds DIG_MAX_BODY_BYTES.

    Two paths:
      1. Content-Length present → fast-reject with 413 before any body
         bytes are read. Catches the common case (pydantic-shaped
         JSON PUTs).
      2. Content-Length missing (chunked/transfer-encoded) → wrap the
         ASGI receive callable to count bytes; bail with 413 the first
         time we'd cross the threshold. Without this, an attacker could
         skip Content-Length and stream forever.

    Multipart uploads (.dpack archives) have their own per-payload cap
    (`_MAX_ARCHIVE_BYTES = 50 MB` in packs.py) — the body cap is a
    coarser outer limit and should always be ≥ the most generous
    per-route cap. If the operator raises one without raising the
    other, the per-route cap still wins, which is fine.
    """

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self._max = max_bytes

    async def dispatch(self, request: Request, call_next):
        # Skip GET/HEAD/DELETE/OPTIONS — bodies on these are unusual and
        # we'd rather not pay the wrapper cost. (POST/PUT/PATCH carry
        # essentially all our write traffic.)
        if request.method in ("GET", "HEAD", "DELETE", "OPTIONS"):
            return await call_next(request)
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self._max:
                    return JSONResponse(
                        {
                            "detail": (
                                f"request body too large: {int(cl):,} bytes "
                                f"(max {self._max:,})"
                            ),
                        },
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse(
                    {"detail": "invalid content-length header"},
                    status_code=400,
                )
        else:
            # Chunked encoding — wrap receive to enforce the cap.
            received = 0
            original_receive = request.receive
            cap = self._max

            async def _capped_receive():
                nonlocal received
                msg = await original_receive()
                if msg.get("type") == "http.request":
                    body = msg.get("body") or b""
                    received += len(body)
                    if received > cap:
                        # Force the consumer to see EOF + an error. We
                        # can't synchronously return a 413 from inside
                        # receive (the request has already begun), so
                        # raise — Starlette's ServerErrorMiddleware
                        # will translate to a 500. The Content-Length
                        # path catches the common case; this is a
                        # belt-and-braces guard.
                        raise ValueError(
                            f"chunked request body exceeded {cap:,} bytes",
                        )
                return msg

            request._receive = _capped_receive  # noqa: SLF001
        return await call_next(request)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Optional bearer-token gate.

    If `DIG_AUTH_TOKEN` is set, every API request must present
    `Authorization: Bearer <token>` (or `?token=...` for WebSocket upgrades,
    which can't carry custom headers reliably). When the token is unset *and*
    the bind host is non-loopback, the app refuses to start (see `run()`).
    """

    def __init__(self, app, token: str | None) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):
        if self._token is None:
            return await call_next(request)
        if request.method == "OPTIONS":  # CORS preflight
            return await call_next(request)
        path = request.url.path
        if path in _AUTH_BYPASS_PATHS:
            return await call_next(request)
        # ``openapi.json`` / ``/docs`` / ``/redoc`` were previously
        # bypassed entirely so a developer could browse the API spec
        # without authenticating. That gives an unauth attacker a free
        # reconnaissance map of every endpoint, parameter, and schema —
        # pen-tester finding round 2 (medium severity). Now gated behind
        # the same Bearer / ?token check as everything else; on a
        # loopback-only dev install (DIG_AUTH_TOKEN unset) the gate
        # is a no-op so dev-time browsing still works. ``/docs-files``
        # serves repo-bundled markdown docs; same treatment.

        # Token is normally supplied via `Authorization: Bearer <token>`. Two
        # categories of client can't reach that header:
        #   - WebSocket upgrades (browsers don't allow custom headers on WS).
        #   - DuckDB-WASM's HTTP fetches for parquet/csv files registered via
        #     `registerFileURL` — the WASM HTTP path emits a fixed Range/Accept
        #     request and there's no API to inject headers.
        # For both, fall back to `?token=…`. The frontend embeds it for
        # registered file URLs (see dispatcher.ts) and ws.ts for the WS path.
        # Header takes precedence so ordinary REST calls aren't tempted to put
        # the token on the URL where it'd leak via referer / log lines.
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            supplied = auth.removeprefix("Bearer ").strip()
        else:
            supplied = request.query_params.get("token")

        if supplied is None or not secrets.compare_digest(supplied, self._token):
            return JSONResponse(
                {"detail": "missing or invalid auth token"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="DIG"'},
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    # Seed built-in notification rules. Idempotent — only adds missing
    # rows, never touches user customisations.
    from dig.api.notification_rules import seed_default_rules
    await seed_default_rules()
    # Force scan of plugin folders on startup so any failures surface early.
    connectors()
    steps()

    # Phase A — emit system.startup event. Notification rules can match
    # this to surface "DIG API started" rows in the panel; default rules
    # don't (would be too noisy on dev with frequent restarts) but a
    # user can add one.
    from dig.api.events import EventKinds, emit_event
    from dig import __version__
    await emit_event(
        EventKinds.SYSTEM_STARTUP,
        version=__version__,
        level="notification",
    )

    # Start the periodic freshness scanner. Runs every 60s; emits
    # transition events that flow through the rule engine.
    from dig.api.freshness_scanner import start_freshness_scanner, stop_freshness_scanner
    scanner_task = start_freshness_scanner()

    yield

    # Graceful shutdown: cancel any in-flight runs and mark them aborted.
    # Without this, SIGTERM / uvicorn reload leaves rows stuck at `running`.
    log.info("shutting down — cancelling %d in-flight run(s)", len(jobs._tasks))  # noqa: SLF001
    await stop_freshness_scanner(scanner_task)
    await jobs.shutdown()
    await emit_event(EventKinds.SYSTEM_SHUTDOWN, level="notification")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DataInsightGrove API",
        version=__version__,
        description="DIG backend API.",
        lifespan=lifespan,
    )

    # CORS origin parsing must trim whitespace per entry — browsers compare
    # origins byte-exactly, so a stray space in `"http://x:3000, http://y"`
    # would make the second origin literally `" http://y"` and silently break
    # all requests from that origin. Drop empty entries too.
    cors_origins = [
        o.strip()
        for o in os.environ.get(
            "DIG_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        # Restrict to what the frontend actually uses — was "*" before.
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        allow_headers=["Authorization", "Content-Type", "If-Match", "If-None-Match", "Accept"],
        max_age=600,
    )

    # Bearer-token gate. Token is optional for loopback bind (default), required
    # for non-loopback (enforced in run()).
    app.add_middleware(BearerAuthMiddleware, token=os.environ.get("DIG_AUTH_TOKEN") or None)

    # Body-size guard. Added *after* (so executed *before* — Starlette
    # runs middleware in reverse-add order) the auth gate so we don't
    # waste cycles parsing a giant body for an unauthenticated client,
    # but the auth gate itself doesn't read the body so the order is
    # cosmetic; the important thing is the cap fires before any of our
    # route handlers buffer the payload.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=_max_body_bytes())

    @app.get("/health", response_model=Health, tags=["meta"])
    async def health() -> Health:
        return Health(status="ok", version=__version__, name="dig")

    @app.get("/connectors", tags=["meta"])
    async def list_connectors() -> list[dict]:
        return [c.manifest for c in connectors().all()]

    # Base physical types — these are first-class targets for `cast_type` but
    # don't have detectors (their identity comes from the polars dtype, not
    # from value-shape inference). Listed here so the /types endpoint can
    # surface the *complete* catalog the UI's "Show all types" view needs.
    # Keep IDs in sync with backend/steps/cast_type/manifest.json:targetType.
    _BASE_TYPE_DESCRIPTORS: list[dict] = [
        {"id": "string",   "label": "🅰️ string",   "base": "string",
         "description": "Text. The catch-all when nothing more specific fits."},
        {"id": "integer",  "label": "🔢 integer",  "base": "integer",
         "description": "Whole numbers (int8/16/32/64)."},
        {"id": "double",   "label": "🔢 double",   "base": "double",
         "description": "Floating-point numbers (float32/64)."},
        {"id": "boolean",  "label": "☑️ boolean",  "base": "boolean",
         "description": "True / false."},
        {"id": "date",     "label": "📅 date",     "base": "date",
         "description": "Calendar date — no time component."},
        {"id": "datetime", "label": "📅 datetime", "base": "datetime",
         "description": "Timestamp — date + time of day."},
    ]

    @app.get("/types", tags=["meta"])
    async def list_types() -> list[dict]:
        """The complete catalog of logical types DIG knows about.

        Returns base physical types first (string, integer, double, boolean,
        date, datetime) followed by every meta-type from the detector
        registry (index, percentage, currency, scientific, hex, uuid, email,
        url, ip, phone, country, color, timezone). Each entry carries an
        id, a UI label (with emoji), the base physical storage type, and a
        one-line dropdown description.

        This endpoint is the single source of truth for the cast UI's
        "Show all types" view. The smart-picks list comes from per-column
        profile candidates (see profile.py + meta_types.detect_candidates),
        which reference the IDs returned here.
        """
        from dig.engine.meta_types import TYPES
        meta = [
            {"id": t.id, "label": t.label, "base": t.base, "description": t.description}
            for t in TYPES
        ]
        return _BASE_TYPE_DESCRIPTORS + meta

    app.include_router(datasets_api.router)
    app.include_router(pipelines_api.router)
    app.include_router(pipelines_api.runs_router)
    app.include_router(pipelines_api.steps_router)
    app.include_router(pipelines_api.ws_router)
    app.include_router(settings_api.router)
    app.include_router(settings_api.drivers_router)
    app.include_router(settings_api.webhooks_router)
    app.include_router(settings_api.fs_router)
    app.include_router(ai_api.router)
    app.include_router(schedules_api.router)
    app.include_router(templates_api.router)
    app.include_router(packs_api.router)
    app.include_router(notifications_api.router)
    app.include_router(notification_rules_api.router)
    app.include_router(catalog_api.router)
    app.include_router(search_api.router)

    # Serve in-repo docs as static files so the frontend's HelpLink components
    # can deep-link to specific sections of getting_started.md, etc.
    docs_dir = Path(__file__).resolve().parents[3] / "docs"
    if docs_dir.is_dir():
        app.mount("/docs-files", StaticFiles(directory=str(docs_dir)), name="docs-files")

    return app


app = create_app()


def run() -> None:
    """Entry point for `dig-api` console script and `python -m dig.api.main`."""
    import uvicorn

    # Resolve host + port from the canonical chain (env → ~/.config/dig/config.json
    # → built-in defaults). Single source of truth lives in dig._settings —
    # do NOT inline a hardcoded fallback here.
    from dig import _settings
    host = _settings.api_host()
    port = _settings.api_port()
    reload = os.environ.get("DIG_RELOAD", "0") == "1"
    token = os.environ.get("DIG_AUTH_TOKEN") or None

    # Refuse to start non-loopback without an auth token. The whole-app threat
    # model assumes either (a) loopback only or (b) a shared secret. Anything
    # else accidentally exposes the user's data dir to the LAN.
    if not _is_loopback(host) and token is None:
        raise SystemExit(
            f"DIG_HOST is set to non-loopback ({host}) but DIG_AUTH_TOKEN is unset.\n"
            "Set DIG_AUTH_TOKEN to a strong random string (e.g. `python3 -c 'import secrets; "
            "print(secrets.token_urlsafe(32))'`) before exposing DIG beyond loopback."
        )

    # Custom logging config that strips ``?token=…`` from access-log query
    # strings before they hit the file handler. Round-3 pen-tester finding:
    # the WS-upgrade path uses ``?token=<secret>`` because browsers can't
    # set custom headers on a WS connect — and uvicorn's default access
    # log writes the full URL including that query string. Anyone with
    # read access to the access log (operators, log-shippers, SIEMs)
    # could harvest tokens. The filter is permissive: it redacts ANY
    # query parameter named ``token`` in any URL, not just WS upgrades.
    import logging as _logging

    class _RedactTokenFilter(_logging.Filter):
        def filter(self, record: _logging.LogRecord) -> bool:
            try:
                msg = record.getMessage()
            except Exception:  # noqa: BLE001
                return True
            if "token=" in msg:
                import re as _re
                redacted = _re.sub(r"token=[^&\s\"']+", "token=<redacted>", msg)
                if redacted != msg:
                    # Replace the args so getMessage returns the redacted form.
                    record.msg = redacted
                    record.args = ()
            return True

    log_config = uvicorn.config.LOGGING_CONFIG
    # Inject the filter onto the access logger.
    log_config.setdefault("filters", {})
    log_config["filters"]["redact_token"] = {"()": _RedactTokenFilter}
    log_config["loggers"].setdefault("uvicorn.access", {}).setdefault("handlers", []).append("default")
    log_config["loggers"]["uvicorn.access"]["filters"] = ["redact_token"]

    # Round-4 DoS #2 — cap WebSocket frame size. Without this, a
    # malicious client could ship a single 4 GiB frame and tie up the
    # event loop while websockets buffers it. 1 MiB is plenty for our
    # WS payloads (the protocol carries pings + small JSON messages
    # only — no file uploads). The cap can be raised by ops via
    # DIG_WS_MAX_BYTES if a future feature genuinely needs bigger
    # frames; the default is intentionally conservative.
    ws_max_size = int(os.environ.get("DIG_WS_MAX_BYTES", str(1024 * 1024)))
    uvicorn.run(
        "dig.api.main:app", host=host, port=port, reload=reload,
        log_config=log_config,
        ws_max_size=ws_max_size,
    )


if __name__ == "__main__":
    run()

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
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


class _RedactTokenFilter(logging.Filter):
    """Strip ``?token=…`` from access-log query strings before they hit the
    file handler. The WS-upgrade path carries the auth token in the query
    string (browsers can't set custom headers on a WS connect), and uvicorn's
    default access log would otherwise write the full URL including the secret.
    Redacts ANY query parameter named ``token`` in any logged URL.

    Defined at module scope (not inside ``run()``) so uvicorn's reloader —
    which spawns the worker via ``multiprocessing`` and must pickle the log
    config — can reference it by dotted path. A local class is unpicklable and
    crashes ``--reload`` startup.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        if "token=" in msg:
            import re as _re
            # Match only URL-safe token characters (RFC 3986 unreserved + a
            # few url-safe extras) so trailing separators some loggers append
            # (``;`` ``]`` ``}`` ``,``) don't leak the credential.
            redacted = _re.sub(
                r"token=[A-Za-z0-9._~+/=\-]+",
                "token=<redacted>",
                msg,
            )
            if redacted != msg:
                # Replace the args so getMessage returns the redacted form.
                record.msg = redacted
                record.args = ()
        return True


def _resolve_auth_token() -> str | None:
    """Read ``DIG_AUTH_TOKEN`` and treat blank-string-after-strip as
    "explicitly cleared" — but ALSO emit a startup warning since a blank
    value in a `.env` file usually indicates a misconfigured operator
    who *thought* they were enforcing auth. Returns None when no token
    is enforced; returns the token string otherwise.

    Pen-tester finding: previously `os.environ.get("DIG_AUTH_TOKEN") or None`
    silently turned `DIG_AUTH_TOKEN=""` (set-but-blank) into None, so an
    operator who put `DIG_AUTH_TOKEN=` in a `.env` file got a wide-open
    server while believing they had locked it down.
    """
    raw = os.environ.get("DIG_AUTH_TOKEN")
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        log.warning(
            "DIG_AUTH_TOKEN is set but blank — auth IS DISABLED. "
            "This is almost always a misconfiguration; either unset the "
            "variable explicitly or set it to a strong random string.",
        )
        return None
    return stripped


class HealthExtension(BaseModel):
    """One discovered extension — entry-point or filesystem.

    Surfaced by /health.extensions[*]. Frontend reads `loaded` to gate UI;
    `load_error` (when set) tells the operator why an extension is silent.
    """
    kind: str  # "entry_point" | "fs"
    name: str
    package: str | None = None         # entry-point only
    package_version: str | None = None  # entry-point only
    group: str | None = None            # entry-point only
    url_prefix: str | None = None       # fs only
    loaded: bool = True
    load_error: str | None = None


class Health(BaseModel):
    status: str
    version: str
    name: str
    # Out-of-tree extensions discovered at startup. Empty without any
    # plugins; populated when a plugin is installed via pip or dropped
    # into data/extensions/.
    extensions: list[HealthExtension] = []
    # Surface-version stamp for the dig.protocols module — extension
    # builds compare their pinned target against this value.
    protocol_version: tuple[int, int] = (1, 0)


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

# Per-route caps for routes that legitimately carry payloads larger than
# the global default. /packs/upload accepts .dpack archives up to the
# 50 MB pack cap (`_MAX_ARCHIVE_BYTES` in dig/plugins/packs.py), plus
# multipart framing overhead — 64 MiB gives the full legal pack range
# headroom while every other route stays at the 32 MiB default. The
# effective limit for a listed route is the larger of this value and
# the global cap, so raising DIG_MAX_BODY_BYTES past 64 MiB still
# applies here too.
_ROUTE_MAX_BODY_BYTES: dict[str, int] = {
    "/packs/upload": 64 * 1024 * 1024,
}


def _max_body_bytes() -> int:
    raw = os.environ.get("DIG_MAX_BODY_BYTES")
    if not raw:
        return _DEFAULT_MAX_BODY_BYTES
    try:
        n = int(raw)
        return n if n > 0 else _DEFAULT_MAX_BODY_BYTES
    except ValueError:
        return _DEFAULT_MAX_BODY_BYTES


class _BodyTooLarge(Exception):
    """Raised from the wrapped ASGI receive once the running body-byte
    total crosses the cap. Carries the total seen so the 413 can report
    it."""

    def __init__(self, received: int) -> None:
        super().__init__(received)
        self.received = received


class BodySizeLimitMiddleware:
    """Reject requests whose body exceeds DIG_MAX_BODY_BYTES.

    Pure ASGI middleware. It sits directly on the raw ASGI receive
    channel that the entire downstream stack (the auth middleware, then
    the matched route) actually pulls body chunks from — so both paths
    are enforced where the bytes really flow, not on a wrapper that the
    server-supplied receive bypasses:

      1. Content-Length present → fast-reject with 413 before any body
         bytes are read. Catches the common case (pydantic-shaped
         JSON PUTs).
      2. Content-Length missing (chunked/transfer-encoded) → the wrapped
         receive counts ``http.request`` body bytes and raises once the
         cap is crossed; the 413 is emitted before the downstream app
         has produced a response (it is still reading the body). Without
         this, an attacker could skip Content-Length and stream forever.

    Routes listed in `_ROUTE_MAX_BODY_BYTES` get a higher cap — the
    larger of the global and per-route values. /packs/upload must admit
    .dpack archives up to the 50 MB pack cap (`_MAX_ARCHIVE_BYTES` in
    dig/plugins/packs.py) plus multipart framing, which the 32 MiB
    default would reject before the endpoint's own cap ever ran.
    Everything else stays at the global cap.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self._max = max_bytes

    async def __call__(self, scope, receive, send):
        # Only HTTP requests carry bodies; pass websocket/lifespan through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Skip GET/HEAD/DELETE/OPTIONS — bodies on these are unusual and
        # we'd rather not pay the wrapper cost. (POST/PUT/PATCH carry
        # essentially all our write traffic.)
        if scope.get("method") in ("GET", "HEAD", "DELETE", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        limit = max(self._max, _ROUTE_MAX_BODY_BYTES.get(scope.get("path", ""), 0))

        # Content-Length fast pre-check — reject before reading any body.
        cl = None
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                cl = value
                break
        if cl is not None:
            try:
                declared = int(cl)
            except ValueError:
                await JSONResponse(
                    {"detail": "invalid content-length header"},
                    status_code=400,
                )(scope, receive, send)
                return
            if declared > limit:
                await JSONResponse(
                    {
                        "detail": (
                            f"request body too large: {declared:,} bytes "
                            f"(max {limit:,})"
                        ),
                    },
                    status_code=413,
                )(scope, receive, send)
                return

        # Chunked / streamed body (or a truthful Content-Length that we
        # still enforce byte-for-byte). Count bytes on the receive the
        # downstream app reads from.
        received = 0

        async def _capped_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body") or b"")
                if received > limit:
                    raise _BodyTooLarge(received)
            return message

        response_started = False

        async def _tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, _capped_receive, _tracked_send)
        except _BodyTooLarge as exc:
            if response_started:
                # The app already began responding before finishing the
                # read — we can't inject a 413 without corrupting the
                # in-flight response, so let it surface.
                raise
            await JSONResponse(
                {
                    "detail": (
                        f"request body too large: {exc.received:,} bytes "
                        f"(max {limit:,})"
                    ),
                },
                status_code=413,
            )(scope, receive, send)


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
        # Default — overwritten below when a valid token is presented.
        # Handlers (e.g. /health) can branch on this to redact extra
        # detail for anonymous callers (round-4 QA finding).
        request.state.auth_ok = False
        if self._token is None:
            # No token configured — everyone is "trusted" (loopback dev mode).
            request.state.auth_ok = True
            return await call_next(request)
        if request.method == "OPTIONS":  # CORS preflight
            return await call_next(request)
        path = request.url.path
        if path in _AUTH_BYPASS_PATHS:
            # Bypass path — handler runs without authentication. Mark
            # the request as anonymous so the handler can self-redact.
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
        request.state.auth_ok = True
        return await call_next(request)


_DISCOVERED_EXTENSIONS: dict[str, Any] = {"entry_points": [], "fs": [], "loaded_objects": []}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Configure structured-or-text logging based on DIG_LOG_FORMAT.
    # Idempotent — safe to call from tests / reloads.
    from dig.observability import configure_logging, set_gauge
    configure_logging()
    set_gauge("dig_dig_version", 1.0, labels={"version": __version__})

    # Discover out-of-tree extensions BEFORE init_db so a future
    # extension can hook into init_db (e.g. an enterprise auth plugin
    # that wants to add its own ALTER TABLE patches). Best-effort —
    # broken extensions are logged + skipped, never block startup.
    from dig.extensions import discover_all
    global _DISCOVERED_EXTENSIONS
    _DISCOVERED_EXTENSIONS = discover_all()
    log.info(
        "discovered %d entry-point extension(s), %d filesystem extension(s)",
        len(_DISCOVERED_EXTENSIONS["entry_points"]),
        len(_DISCOVERED_EXTENSIONS["fs"]),
    )

    await init_db()
    # Detect a version transition since the prior boot (e.g. after a
    # `./upgrade.sh` run). Updates the marker file + emits an event
    # when the version changed. init_db has already run the additive
    # schema patches that any upgrade might require — this hook is the
    # *signal* that a transition happened, not the migration engine.
    from dig.storage.version_state import detect_and_record_version_transition
    await detect_and_record_version_transition()
    # Repair datasets stranded by an unclean shutdown. An ingest that was
    # in flight when the previous process died (kill -9, power loss — the
    # graceful path in jobs.shutdown() never ran) leaves its row stuck at
    # status='ingesting' forever, and the UI shows a spinner that never
    # resolves. Mirror of the run-abort repair in JobManager.shutdown():
    # a fresh boot can have no legitimately in-flight ingest, so mark
    # them all failed.
    from datetime import datetime, timezone

    from sqlalchemy import update as sa_update

    from dig.storage.db import SessionLocal
    from dig.storage.models import Dataset, Run
    async with SessionLocal() as session:
        res = await session.execute(
            sa_update(Dataset)
            .where(Dataset.status == "ingesting")
            .values(status="failed", error="interrupted by restart"),
        )
        await session.commit()
        if res.rowcount:
            log.info(
                "boot sweep: marked %d dataset(s) stranded at 'ingesting' as failed",
                res.rowcount,
            )
        # Same repair for runs. A hard kill (kill -9, power loss) skips
        # JobManager.shutdown(), leaving rows stuck at 'running'/'queued' —
        # the exact non-terminal states the manager treats as in-flight
        # (terminal set: succeeded/failed/cancelled). The UI then spins on
        # a run that will never resume. A fresh boot has no legitimately
        # in-flight run, so mark them all failed.
        res = await session.execute(
            sa_update(Run)
            .where(Run.status.in_(("running", "queued")))
            .values(
                status="failed",
                error="interrupted by restart",
                finished_at=datetime.now(timezone.utc),
            ),
        )
        await session.commit()
        if res.rowcount:
            log.info(
                "boot sweep: marked %d run(s) stranded at 'running'/'queued' as failed",
                res.rowcount,
            )
    # Clear the transient preview caches left by the previous process.
    # __preview holds fingerprint-keyed Polars-ancestor parquets for canvas
    # focus; __ai_samples holds the same for AI node-context sampling. Both are
    # rebuilt on demand — wiping them on boot bounds their size and guarantees a
    # step-code change across a restart can never serve a stale cached result.
    # Best-effort — never block startup.
    try:
        from dig.storage.files import data_dir as _pv_data_dir
        import shutil as _pv_shutil
        _outputs = _pv_data_dir() / "outputs"
        for _cache_name in ("__preview", "__ai_samples"):
            _cache_root = _outputs / _cache_name
            if _cache_root.exists():
                _pv_shutil.rmtree(_cache_root, ignore_errors=True)
                log.info("boot sweep: cleared preview cache at %s", _cache_root)
    except Exception:
        log.exception("boot sweep: failed clearing preview caches (non-fatal)")

    # Seed built-in notification rules. Idempotent — only adds missing
    # rows, never touches user customisations.
    from dig.api.notification_rules import seed_default_rules
    await seed_default_rules()
    # Force scan of plugin folders on startup so any failures surface early.
    connectors()
    steps()

    # Emit system.startup event. Notification rules can match
    # this to surface "DIG API started" rows in the panel; default rules
    # don't (would be too noisy on dev with frequent restarts) but a
    # user can add one.
    from dig.api.events import EventKinds, emit_event
    # __version__ is already imported at module top — re-importing here
    # was making Python treat it as a local for the whole function scope
    # (which broke the earlier set_gauge call referencing it).
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
    # Release the shared AI HTTP client's pooled connections.
    from dig.ai.client import aclose_client

    await aclose_client()
    await emit_event(EventKinds.SYSTEM_SHUTDOWN, level="notification")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DataInsightGrove API",
        version=__version__,
        description="DIG backend API.",
        lifespan=lifespan,
    )

    # CORS origin parsing must trim whitespace per entry — browsers compare
    # origins byte-exactly, so a stray space in `"http://x:3100, http://y"`
    # would make the second origin literally `" http://y"` and silently break
    # all requests from that origin. Drop empty entries too.
    cors_origins = [
        o.strip()
        for o in os.environ.get(
            "DIG_CORS_ORIGINS",
            "http://localhost:3100,http://127.0.0.1:3100",
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
    app.add_middleware(BearerAuthMiddleware, token=_resolve_auth_token())

    # Body-size guard. Added *after* (so executed *before* — Starlette
    # runs middleware in reverse-add order) the auth gate so we don't
    # waste cycles parsing a giant body for an unauthenticated client,
    # but the auth gate itself doesn't read the body so the order is
    # cosmetic; the important thing is the cap fires before any of our
    # route handlers buffer the payload.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=_max_body_bytes())

    @app.get("/health", response_model=Health, tags=["meta"])
    async def health(request: Request) -> Health:
        from dig.protocols import PROTOCOL_VERSION

        # Round-4 QA finding: ``/health`` is in ``_AUTH_BYPASS_PATHS`` so
        # any LAN-reachable scanner can fetch it. The previous shape
        # leaked package name + version + group of every installed
        # extension, which is dependency-fingerprint gold for a chained
        # CVE attack ("oh, this DIG ships dig-enterprise-rcN; CVE-2026-…"
        # applies). Detailed fields stay behind auth; unauthenticated
        # callers see only counts + a generic "loaded/failed" mix.
        is_authed = bool(getattr(request.state, "auth_ok", False))

        ext_records: list[HealthExtension] = []
        for ep in _DISCOVERED_EXTENSIONS.get("entry_points", []):
            if is_authed:
                ext_records.append(HealthExtension(
                    kind="entry_point",
                    name=ep["name"],
                    package=ep["package"],
                    package_version=ep["package_version"],
                    group=ep["group"],
                    loaded=ep["loaded"],
                    load_error=ep["load_error"],
                ))
            else:
                ext_records.append(HealthExtension(
                    kind="entry_point",
                    name="<redacted>",
                    loaded=ep["loaded"],
                ))
        for fs in _DISCOVERED_EXTENSIONS.get("fs", []):
            if is_authed:
                ext_records.append(HealthExtension(
                    kind="fs",
                    name=fs["name"],
                    url_prefix=fs["url_prefix"],
                    loaded=fs["load_error"] is None,
                    load_error=fs["load_error"],
                ))
            else:
                ext_records.append(HealthExtension(
                    kind="fs",
                    name="<redacted>",
                    loaded=fs["load_error"] is None,
                ))
        return Health(
            status="ok", version=__version__, name="dig",
            extensions=ext_records,
            protocol_version=PROTOCOL_VERSION,
        )

    @app.get("/metrics", tags=["meta"], include_in_schema=False)
    async def metrics():
        """Prometheus text-format metrics scrape endpoint.

        Exposes counters / gauges / histograms registered in
        ``dig.observability.metrics``. The OSS install pre-declares a
        handful of pipeline-run + NaN-production counters; emit sites
        elsewhere in the codebase contribute observations. No external
        Prometheus SDK required — minimal text format.
        """
        from fastapi.responses import PlainTextResponse

        from dig.observability import render_prometheus

        return PlainTextResponse(
            render_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8"
        )

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

    # ── Out-of-tree extension wiring ────────────────────────────────────
    #
    # Two channels (see dig/extensions/loader.py):
    #
    #  1. `dig.routers` entry points → FastAPI routers contributed by
    #     out-of-tree packages (e.g. dig-enterprise's audit-log router,
    #     /users, /orgs, /billing routes).
    #  2. `data/extensions/<name>/static/` directories → static-file
    #     overlays mounted at `/ext/<name>/static/*`. Used by enterprise
    #     to inject extra JS/CSS without touching the OSS repo.
    #
    # The discovery already happened in lifespan(); we just attach what
    # was found. Routers from failed-to-load packages are simply absent
    # — surfaced in /health.extensions[*].load_error for the operator.
    from dig.extensions import discover_all
    _ext = discover_all()
    for ep in _ext["loaded_objects"]:
        if ep.group != "dig.routers" or ep.loaded_object is None:
            continue
        try:
            app.include_router(ep.loaded_object)
            log.info("mounted router from extension %s (%s)", ep.name, ep.package)
        except Exception:
            log.exception(
                "failed to mount router from extension %s — skipping", ep.name,
            )
    for fs in _ext["fs"]:
        if not fs["has_static"] or fs["load_error"] is not None:
            continue
        static_path = Path(fs["path"]) / "static"
        # Symlink-rejection at mount time. Pen-tester finding: Starlette's
        # StaticFiles follows symlinks by default, so `data/extensions/foo/
        # static/secrets -> /etc/secrets` would be served at /ext/foo/static
        # /secrets. Resolve the static dir + every immediate child; bail if
        # anything points outside the extension's own root.
        try:
            ext_root = Path(fs["path"]).resolve()
            resolved_static = static_path.resolve()
            resolved_static.relative_to(ext_root)
            for child in resolved_static.iterdir():
                child_resolved = child.resolve()
                child_resolved.relative_to(ext_root)
        except (ValueError, OSError):
            log.warning(
                "extension %s: static/ contains symlink escaping its own root; "
                "refusing to mount", fs["name"],
            )
            continue
        try:
            app.mount(
                f"{fs['url_prefix']}/static",
                StaticFiles(directory=str(static_path), follow_symlink=False),
                name=f"ext-{fs['name']}",
            )
            log.info("mounted /ext/%s/static -> %s", fs["name"], static_path)
        except TypeError:
            # `follow_symlink` may not exist on older Starlette versions;
            # fall back to the symlink-scan above as our only defence.
            try:
                app.mount(
                    f"{fs['url_prefix']}/static",
                    StaticFiles(directory=str(static_path)),
                    name=f"ext-{fs['name']}",
                )
                log.info("mounted /ext/%s/static -> %s (no follow_symlink kwarg)", fs["name"], static_path)
            except Exception:
                log.exception(
                    "failed to mount static dir for extension %s — skipping", fs["name"],
                )
        except Exception:
            log.exception(
                "failed to mount static dir for extension %s — skipping", fs["name"],
            )

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
    token = _resolve_auth_token()

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
    # strings before they hit the file handler (see _RedactTokenFilter at
    # module scope). Referenced by dotted path — a factory ``"()"`` value —
    # rather than the class object, so uvicorn's spawn-based reloader can
    # pickle the log config without crashing.
    log_config = uvicorn.config.LOGGING_CONFIG
    # Inject the filter onto the access logger.
    log_config.setdefault("filters", {})
    log_config["filters"]["redact_token"] = {"()": "dig.api.main._RedactTokenFilter"}
    log_config["loggers"].setdefault("uvicorn.access", {}).setdefault("handlers", []).append("default")
    log_config["loggers"]["uvicorn.access"]["filters"] = ["redact_token"]

    # Round-3 operational finding: configure_logging() makes the root
    # logger emit structured JSON when ``DIG_LOG_FORMAT=json`` is set,
    # but uvicorn ships its OWN LOGGING_CONFIG and its access logger
    # used a plain-text formatter regardless. Operators piping logs
    # into ``jq`` got mixed lines (DIG = JSON, uvicorn = ascii table).
    # When JSON mode is on, swap uvicorn's two formatters to the same
    # JsonFormatter the rest of DIG uses.
    from dig.observability.logging_setup import is_json_logging
    if is_json_logging():
        log_config.setdefault("formatters", {})["dig_json"] = {
            "()": "dig.observability.logging_setup.JsonFormatter",
        }
        for handler_name in ("default", "access"):
            handler_cfg = log_config.get("handlers", {}).get(handler_name)
            if handler_cfg is not None:
                handler_cfg["formatter"] = "dig_json"

    # Round-4 DoS #2 — cap WebSocket frame size. Without this, a
    # malicious client could ship a single 4 GiB frame and tie up the
    # event loop while websockets buffers it. 1 MiB is plenty for our
    # WS payloads (the protocol carries pings + small JSON messages
    # only — no file uploads). The cap can be raised by ops via
    # DIG_WS_MAX_BYTES if a future feature genuinely needs bigger
    # frames; the default is intentionally conservative.
    ws_max_size = int(os.environ.get("DIG_WS_MAX_BYTES", str(1024 * 1024)))

    # Uvicorn serves plain HTTP. TLS termination — when enabled — is
    # handled by ``scripts/dig_tls_proxy.py`` which runs as a sibling
    # process: it terminates HTTPS on a separate port (api.httpsPort)
    # and forwards plain HTTP to us. That keeps uvicorn's signal /
    # job-manager / WebSocket state in one place and avoids running two
    # API instances against the same SQLite DB.
    # In dev (--reload), scope the file watcher to the backend source trees.
    # Left unscoped, uvicorn watches the whole cwd (backend/, including the
    # multi-thousand-file .venv) and restarts the worker — a full cold-cache
    # respawn — on any *.py touch. We watch backend/dig (the package) AND
    # backend/steps (the built-in step implementations, a sibling dir that the
    # registry loads) so editing either still hot-reloads, while .venv, tests,
    # and data/build artifacts no longer trigger spurious cold restarts.
    # `reload=False` ignores these entirely.
    reload_kwargs: dict[str, Any] = {}
    if reload:
        _backend_root = Path(__file__).resolve().parents[2]  # .../backend
        reload_kwargs["reload_dirs"] = [
            str(_backend_root / "dig"),
            str(_backend_root / "steps"),
        ]
        reload_kwargs["reload_excludes"] = [
            "*.parquet", "*.sqlite*", "*.log", ".venv/*", "__pycache__/*", "data/*",
        ]
    uvicorn.run(
        "dig.api.main:app", host=host, port=port, reload=reload,
        log_config=log_config,
        ws_max_size=ws_max_size,
        **reload_kwargs,
    )


if __name__ == "__main__":
    run()

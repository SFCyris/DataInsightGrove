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
from dig.api import datasets as datasets_api
from dig.api import pipelines as pipelines_api
from dig.api import settings as settings_api
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
        # Static doc files are public — they're literal repo docs.
        if path.startswith("/docs-files/") or path in ("/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # WebSocket: token via query string (browsers can't set headers on WS).
        if path.startswith("/ws/"):
            supplied = request.query_params.get("token")
        else:
            auth = request.headers.get("authorization", "")
            supplied = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None

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
    # Force scan of plugin folders on startup so any failures surface early.
    connectors()
    steps()
    yield
    # Graceful shutdown: cancel any in-flight runs and mark them aborted.
    # Without this, SIGTERM / uvicorn reload leaves rows stuck at `running`.
    log.info("shutting down — cancelling %d in-flight run(s)", len(jobs._tasks))  # noqa: SLF001
    await jobs.shutdown()


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

    @app.get("/health", response_model=Health, tags=["meta"])
    async def health() -> Health:
        return Health(status="ok", version=__version__, name="dig")

    @app.get("/connectors", tags=["meta"])
    async def list_connectors() -> list[dict]:
        return [c.manifest for c in connectors().all()]

    app.include_router(datasets_api.router)
    app.include_router(pipelines_api.router)
    app.include_router(pipelines_api.runs_router)
    app.include_router(pipelines_api.steps_router)
    app.include_router(pipelines_api.ws_router)
    app.include_router(settings_api.router)
    app.include_router(settings_api.drivers_router)
    app.include_router(settings_api.webhooks_router)
    app.include_router(settings_api.fs_router)

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

    host = os.environ.get("DIG_HOST", "127.0.0.1")
    port = int(os.environ.get("DIG_PORT", "8080"))
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

    uvicorn.run("dig.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()

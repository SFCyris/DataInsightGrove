# DIG backend

The Python half of [DataInsightGrove](../README.md) — a FastAPI service that runs your pipelines, talks to your data, and serves the JSON the frontend lives off.

This README is for contributors and curious developers. **End users don't need to read it** — the repo-root scripts (`./install.sh`, `./start.sh`, `./stop.sh`) take care of everything below.

## Setup

The friendly path:

```bash
# from repo root
./install.sh         # creates backend/.venv and installs all extras
./start.sh           # brings up the API (and the web UI)
```

Or, if you only want the backend and want it in foreground for hot-reload during iteration:

```bash
make backend-setup   # creates .venv and installs the dev extras
make backend-dev     # runs uvicorn with reload at http://127.0.0.1:8090
```

Or fully manually:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[engine,storage,connectors,visualize,ml,dev]'
DIG_RELOAD=1 dig-api
```

## Endpoints

- `GET /health` — service liveness, returns `{"status":"ok","version":"…","name":"dig"}`
- `GET /docs` — Swagger UI
- `GET /openapi.json` — OpenAPI schema (consumed by the frontend's typed client)

## Layout

- `dig/api/` — FastAPI routers
- `dig/engine/` — pipeline model, DAG, executor, registry, lineage
- `dig/jobs/` — asyncio job manager + SQLite-backed job table + webhook dispatch
- `dig/storage/` — async SQLAlchemy + filesystem backend
- `dig/plugins/` — third-party plugin loader (drop a folder under `plugins/steps/` or `plugins/connectors/`)
- `../steps/<id>/` — built-in step plugins
- `../connectors/<id>/` — built-in connector plugins

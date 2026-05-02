# DIG backend

Python execution engine + FastAPI surface.

## Setup

```bash
# from repo root
make backend-setup    # creates .venv and installs the dev extras
make backend-dev      # runs uvicorn with reload at http://127.0.0.1:8090
```

Or manually:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
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

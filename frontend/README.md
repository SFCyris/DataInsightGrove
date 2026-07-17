# DIG frontend

The browser half of [DataInsightGrove](../README.md) — the editor, grid, canvas, settings UI, and everything else you see when you open `http://localhost:3100`.

This README is for contributors and curious developers. **End users don't need to read it** — `./install.sh` and `./start.sh` from the repo root take care of everything below.

Built with Next.js 16 (App Router), React 19, TypeScript, Tailwind v4, shadcn/ui, AG Grid Community for the data grid, React Flow for the canvas, and DuckDB-WASM as the in-browser preview engine.

## Run

The frontend is started by the repo-root scripts as part of the full stack:

```bash
./install.sh    # one-time: pnpm install + DuckDB-WASM bundle copy
./start.sh      # API + web together, detached
```

To run only the web dev server (e.g. while iterating on UI without
restarting the API):

```bash
cd frontend
pnpm dev --port 3100 --hostname 127.0.0.1
```

The dev server expects an API at `NEXT_PUBLIC_DIG_API` (default
`http://127.0.0.1:8190`).

## Layout

- `app/` — Next.js App Router routes (home, projects, datasets, pipelines, settings).
- `components/` — UI components (grid, canvas, param form, column menu, server-status overlay, …).
- `lib/` — TypeScript helpers (API client, WebSocket subscribe, DuckDB-WASM bootstrap, settings store, meta-types, …).
- `public/duckdb-wasm/` — pinned DuckDB-WASM bundles (copied from `node_modules` at install time by `scripts/copy-duckdb-wasm.mjs`; gitignored).

## Build

```bash
pnpm build      # production bundle into .next/
```

Type-check only: `pnpm typecheck` (or `npx tsc --noEmit`).

See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the
backend ↔ frontend contract and [`../docs/UI_GUIDELINES.md`](../docs/UI_GUIDELINES.md)
for the visual design conventions.

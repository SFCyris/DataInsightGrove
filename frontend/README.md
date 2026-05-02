# DIG frontend

The Next.js + React + TypeScript UI for [DataInsightGrove](../README.md).

Built with Next.js 16 (App Router), React 19, Tailwind v4, shadcn/ui,
AG Grid Community, React Flow, and DuckDB-WASM (in-browser preview engine).

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
pnpm dev --port 3000 --hostname 127.0.0.1
```

The dev server expects an API at `NEXT_PUBLIC_DIG_API` (default
`http://127.0.0.1:8080`).

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

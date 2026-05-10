"use client";

import * as duckdb from "@duckdb/duckdb-wasm";

let _dbPromise: Promise<duckdb.AsyncDuckDB> | null = null;

/**
 * Build the bundle map ourselves, pointing at locally-served files under
 * `/duckdb-wasm/`. The wasm + worker pairs are copied from
 * `node_modules/@duckdb/duckdb-wasm/dist/` into `frontend/public/duckdb-wasm/`
 * by `scripts/copy-duckdb-wasm.mjs` (runs on dev/build/postinstall).
 *
 * Why we don't use `getJsDelivrBundles()`: DIG is a self-hosted tool — we
 * shouldn't phone a third-party CDN at runtime. Decision in
 * docs/DECISIONS/0001-duckdb-wasm-hosting.md (Option B: bundle all variants).
 *
 * URLs MUST be absolute. Reason: the worker is created from a Blob URL
 * (see getDb() below), and inside that blob context `importScripts("/foo")`
 * resolves the relative path against the BLOB url itself — not the page
 * origin — and fails to load. Same for wasm fetch from inside the worker.
 * Origin-prefixing fixes both.
 */
function localBundles(): duckdb.DuckDBBundles {
  // SSR safety: window is undefined during pre-render. We ship empty paths
  // in that case; getDb() is only ever called from a "use client" effect so
  // this branch never actually serves bundle data on the server.
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return {
    mvp: {
      mainModule: `${origin}/duckdb-wasm/duckdb-mvp.wasm`,
      mainWorker: `${origin}/duckdb-wasm/duckdb-browser-mvp.worker.js`,
    },
    eh: {
      mainModule: `${origin}/duckdb-wasm/duckdb-eh.wasm`,
      mainWorker: `${origin}/duckdb-wasm/duckdb-browser-eh.worker.js`,
    },
    coi: {
      mainModule: `${origin}/duckdb-wasm/duckdb-coi.wasm`,
      mainWorker: `${origin}/duckdb-wasm/duckdb-browser-coi.worker.js`,
      pthreadWorker: `${origin}/duckdb-wasm/duckdb-browser-coi.pthread.worker.js`,
    },
  };
}

/** Returns a singleton AsyncDuckDB. First call boots the wasm worker (slow);
 * subsequent calls return the same instance.
 *
 * On rejection (e.g., transient network error fetching the wasm), we clear
 * the singleton so the next call retries from scratch. Without this, a
 * single failed boot would freeze the in-browser preview engine until the
 * user manually reloads the page. */
export function getDb(): Promise<duckdb.AsyncDuckDB> {
  if (_dbPromise) return _dbPromise;
  _dbPromise = (async () => {
    const bundle = await duckdb.selectBundle(localBundles());
    const workerUrl = URL.createObjectURL(
      new Blob([`importScripts(${JSON.stringify(bundle.mainWorker!)});`], {
        type: "text/javascript",
      }),
    );
    const worker = new Worker(workerUrl);
    const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(), worker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(workerUrl);
    return db;
  })();
  // On rejection, drop the cached promise so the next caller gets a fresh
  // boot attempt instead of being permanently stuck on the same error.
  _dbPromise.catch(() => {
    _dbPromise = null;
  });
  return _dbPromise;
}

export async function resetDb(): Promise<void> {
  if (_dbPromise) {
    const db = await _dbPromise;
    await db.terminate();
    _dbPromise = null;
  }
}

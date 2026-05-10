"use client";

import * as duckdb from "@duckdb/duckdb-wasm";
import { tableFromIPC, type Table } from "apache-arrow";
import { API_BASE, API_TOKEN, api } from "@/lib/api/client";
import { wrapWithSampling, type SamplingConfig } from "@/lib/sampling";
import { getDb } from "./duckdb";

export interface PreviewResult {
  columns: Array<{ name: string; type: string }>;
  rows: Array<Record<string, unknown>>;
  rowCount: number;
  sampleRows: number;
  elapsedMs: number;
  /** True when the preview ran in DuckDB-WASM (browser); false when it
   *  fell back to the backend (e.g. spatial extension required). */
  ranLocally: boolean;
}

// Functions / types that the bundled DuckDB-WASM build doesn't have without
// the spatial extension. When the compiled SQL contains any of these, we
// proactively skip DuckDB-WASM (which would fail with a confusing
// "function not found" error) and surface a clear "via backend" status to
// the caller. Loading the spatial extension into the WASM build is
// possible (~12 MB extra .wasm) but a deliberate trade-off we don't make
// by default.
const _SPATIAL_TOKENS = [
  "GEOMETRY",
  "ST_DISTANCE", "ST_DWITHIN", "ST_CONTAINS", "ST_INTERSECTS", "ST_BUFFER",
  "ST_POINT", "ST_X", "ST_Y", "ST_TRANSFORM", "ST_GEOMFROMTEXT", "ST_GEOMFROMWKB",
  "ST_AREA", "ST_LENGTH", "ST_CENTROID", "ST_UNION",
];

export function requiresSpatialExtension(sql: string): boolean {
  const upper = sql.toUpperCase();
  return _SPATIAL_TOKENS.some((tok) => upper.includes(tok));
}

/** Compile a pipeline server-side, fetch the required parquet/csv files, register them
 * in DuckDB-WASM, run the SQL, and return a preview page.
 *
 * `terminal` selects which step's output to show (defaults to last step). Used by
 * the live grid's focused-step view so users can see the data after each step. */
export async function previewPipeline(
  pipelineId: string,
  opts: {
    sampleRows?: number;
    previewLimit?: number;
    terminal?: string;
    signal?: AbortSignal;
    sampling?: SamplingConfig | null;
    /** When set, the dispatcher knows whether the focused step is
     *  chart-producing. For chart-producing steps we skip the
     *  rows-fallback because the user wants the chart image preview
     *  (handled by `StepImageOrFallback`), not the underlying rows. */
    terminalStepId?: string;
    /** When the terminal node is a join, the diagnostic preview can be
     *  flipped to show only the unmatched left or right rows (anti-*).
     *  No-op for non-join terminals. */
    terminalViewMode?: "matched" | "unmatched_left" | "unmatched_right";
  } = {},
): Promise<PreviewResult> {
  const sampleRows = opts.sampleRows ?? 100_000;
  const previewLimit = opts.previewLimit ?? 500;

  // Pass the abort signal so the actual fetch can be cancelled mid-flight
  // — not just short-circuited after the response arrives. Without this,
  // typing fast through 5 nodes piles up 5 in-flight compile POSTs server-side.
  let compile;
  try {
    compile = await api.fetchCompile(
      pipelineId, sampleRows, opts.terminal, opts.signal, opts.terminalViewMode,
    );
  } catch (err) {
    if (opts.signal?.aborted) throw new DOMException("aborted", "AbortError");
    // Transparent fallback for Polars-only steps. The backend's
    // compile_for_browser raises:
    //   "step '<id>' has browser engine 'polars'; only 'sql' is supported"
    // for steps like anomaly_zscore, forecast, rolling, seasonal_decompose,
    // changepoint_detection, etc. From the user's perspective they don't
    // care that DuckDB-WASM can't run it — if the backend CAN, we should
    // just route there and stream rows back into the same grid.
    //
    // Exception: chart-producing steps (export_to_image, forecast,
    // seasonal_decompose) — the user wants the rendered chart image,
    // not the underlying rows. The editor's StepImageOrFallback path
    // handles those by rendering the image inline. We let the error
    // bubble for these so that path triggers.
    //
    // Why a hard step-id list (not a category-based check): kmeans,
    // pca, tsne, dbscan all live in `model` and have `render` params
    // too, but their primary output is the row-level scoring/clustering
    // dataframe — users expect rows in the grid, not a chart preview.
    // Forecast + seasonal_decompose are the genuine chart-first steps
    // in the model category.
    const msg = (err as Error).message ?? "";
    const isPolarsOnlyError = /has\s+browser\s+engine\s+'(?:polars|none)'/i.test(msg);
    const chartFirst = new Set([
      "export_to_image",
      "forecast",
      "seasonal_decompose",
    ]);
    const isChartFirst =
      opts.terminalStepId != null && chartFirst.has(opts.terminalStepId);
    if (isPolarsOnlyError && opts.terminal && !isChartFirst) {
      return previewStepOnBackend(pipelineId, opts);
    }
    throw err;
  }
  if (opts.signal?.aborted) throw new DOMException("aborted", "AbortError");

  // Pre-flight check: if the compiled SQL touches the spatial extension,
  // skip DuckDB-WASM (which would fail with "function not found") and run
  // the preview on the backend instead — same shape, slightly slower but
  // transparent to the user. The grid surfaces a small "via backend"
  // badge based on the `ranLocally: false` flag.
  if (requiresSpatialExtension(compile.sql)) {
    return previewOnBackend(pipelineId, opts);
  }

  const db = await getDb();
  const conn = await db.connect();

  const t0 = performance.now();
  try {
    // Register each binding as a virtual file pointing at the API URL.
    // DuckDB-WASM emits its own HTTP requests for these files and has no
    // hook for adding headers — so when the backend has DIG_AUTH_TOKEN set
    // (--global mode), we attach the token via `?token=…`. The backend's
    // BearerAuthMiddleware accepts that as a fallback when no Authorization
    // header is present. Without this, the parquet fetch returns 401 and
    // DuckDB-WASM silently shows an empty grid for non-chart steps.
    for (const f of compile.files) {
      let url = f.url.startsWith("http") ? f.url : `${API_BASE}${f.url}`;
      if (API_TOKEN) {
        const sep = url.includes("?") ? "&" : "?";
        url = `${url}${sep}token=${encodeURIComponent(API_TOKEN)}`;
      }
      // Always (re)register — DuckDB-WASM dedupes by name.
      await db.registerFileURL(f.name, url, duckdb.DuckDBDataProtocol.HTTP, false);
    }

    // Wrap the compiled SQL with the user-chosen sampling method for
    // the grid. When `opts.sampling` is provided (the editor passes the
    // doc's metadata.sampling here), the compiled pipeline output is
    // sampled accordingly, then a previewLimit is applied so the grid
    // never tries to render more than ~500 rows. When sampling is not
    // set, we fall back to the historical "first N" behavior.
    const sampledInner = opts.sampling
      ? wrapWithSampling(compile.sql, opts.sampling)
      : compile.sql;
    const previewSql = `SELECT * FROM (${sampledInner}) AS __preview LIMIT ${previewLimit}`;
    const arrow = await conn.query(previewSql);
    const table = arrow as unknown as Table;
    const columns = table.schema.fields.map((f) => ({
      name: f.name,
      type: String(f.type),
    }));
    const rows: Array<Record<string, unknown>> = [];
    for (let i = 0; i < table.numRows; i++) {
      const obj: Record<string, unknown> = {};
      for (const f of table.schema.fields) {
        let v = table.getChild(f.name)?.get(i);
        if (typeof v === "bigint") v = Number(v);
        if (v && typeof (v as { toJSON?: unknown }).toJSON === "function") {
          v = (v as { toJSON: () => unknown }).toJSON();
        }
        obj[f.name] = v;
      }
      rows.push(obj);
    }

    if (opts.signal?.aborted) throw new DOMException("aborted", "AbortError");

    // Total row count for the sampled pipeline (within the sample).
    const countSql = `SELECT count(*) AS c FROM (${sampledInner}) AS __pipeline`;
    const countArrow = await conn.query(countSql);
    const countTable = countArrow as unknown as Table;
    const rowCount = Number(countTable.getChild("c")?.get(0) ?? 0);
    const elapsedMs = Math.round(performance.now() - t0);
    return {
      columns,
      rows,
      rowCount,
      sampleRows,
      elapsedMs,
      ranLocally: true,
    };
  } finally {
    await conn.close();
  }
}

/** Backend-side single-step preview for Polars-only terminals.
 *  Materialises the upstream as Polars frames, runs the focused step's
 *  `execute_polars`, and returns its DataFrame as rows. The grid renders
 *  it identically to a WASM result; the only difference is the "via
 *  backend" badge from `ranLocally: false`. */
async function previewStepOnBackend(
  pipelineId: string,
  opts: { sampleRows?: number; previewLimit?: number; terminal?: string; signal?: AbortSignal },
): Promise<PreviewResult> {
  const sampleRows = opts.sampleRows ?? 20000;
  const previewLimit = opts.previewLimit ?? 500;
  const t0 = performance.now();
  const res = await api.previewStepRows(pipelineId, {
    terminal: opts.terminal!,
    sampleRows,
    previewLimit,
    signal: opts.signal,
  });
  return {
    columns: res.columns,
    rows: res.rows,
    rowCount: res.rowCount,
    sampleRows: res.sampleRows ?? sampleRows,
    elapsedMs: res.elapsedMs ?? Math.round(performance.now() - t0),
    ranLocally: false,
  };
}

/** Backend-side preview — DuckDB on the server runs the same compiled SQL
 *  with the spatial extension loaded. Returns rows in the PreviewResult shape
 *  with `ranLocally: false` so the grid can show a "via backend" badge. */
async function previewOnBackend(
  pipelineId: string,
  opts: { sampleRows?: number; previewLimit?: number; terminal?: string; signal?: AbortSignal },
): Promise<PreviewResult> {
  const sampleRows = opts.sampleRows ?? 100_000;
  const res = await api.previewOnBackend(pipelineId, {
    sampleRows,
    previewLimit: opts.previewLimit ?? 500,
    terminal: opts.terminal,
    signal: opts.signal,
  });
  return {
    columns: res.columns,
    rows: res.rows,
    rowCount: res.rowCount,
    sampleRows: res.sampleRows ?? sampleRows,
    elapsedMs: res.elapsedMs,
    ranLocally: false,
  };
}

"use client";

import * as duckdb from "@duckdb/duckdb-wasm";
import { tableFromIPC, type Table } from "apache-arrow";
import { API_BASE, api } from "@/lib/api/client";
import { getDb } from "./duckdb";

export interface PreviewResult {
  columns: Array<{ name: string; type: string }>;
  rows: Array<Record<string, unknown>>;
  rowCount: number;
  sampleRows: number;
  elapsedMs: number;
  ranLocally: true;
}

/** Compile a pipeline server-side, fetch the required parquet/csv files, register them
 * in DuckDB-WASM, run the SQL, and return a preview page.
 *
 * `terminal` selects which step's output to show (defaults to last step). Used by
 * the live grid's focused-step view so users can see the data after each step. */
export async function previewPipeline(
  pipelineId: string,
  opts: { sampleRows?: number; previewLimit?: number; terminal?: string; signal?: AbortSignal } = {},
): Promise<PreviewResult> {
  const sampleRows = opts.sampleRows ?? 100_000;
  const previewLimit = opts.previewLimit ?? 500;

  // Pass the abort signal so the actual fetch can be cancelled mid-flight
  // — not just short-circuited after the response arrives. Without this,
  // typing fast through 5 nodes piles up 5 in-flight compile POSTs server-side.
  const compile = await api.fetchCompile(pipelineId, sampleRows, opts.terminal, opts.signal);
  if (opts.signal?.aborted) throw new DOMException("aborted", "AbortError");
  const db = await getDb();
  const conn = await db.connect();

  const t0 = performance.now();
  try {
    // Register each binding as a virtual file pointing at the API URL.
    for (const f of compile.files) {
      const url = f.url.startsWith("http") ? f.url : `${API_BASE}${f.url}`;
      // Always (re)register — DuckDB-WASM dedupes by name.
      await db.registerFileURL(f.name, url, duckdb.DuckDBDataProtocol.HTTP, false);
    }

    // Wrap the compiled SQL with a preview LIMIT for the grid.
    const previewSql = `SELECT * FROM (${compile.sql}) AS __pipeline LIMIT ${previewLimit}`;
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

    // Total row count for the un-LIMIT'd pipeline (within the sample).
    const countSql = `SELECT count(*) AS c FROM (${compile.sql}) AS __pipeline`;
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

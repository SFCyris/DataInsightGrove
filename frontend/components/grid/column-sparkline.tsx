"use client";

import { useEffect, useMemo, useRef } from "react";

/**
 * Compact 60×16 sparkline rendered on canvas. Computes bins client-side
 * from the rows already in browser memory — cheap for 10K-row previews.
 *
 * Numeric columns: 16-bin equal-width histogram.
 * Categorical (string/boolean) columns: top-8 bars by frequency.
 *
 * Renders to a single canvas element to avoid per-bar React reconciliation;
 * the full Plot histogram already lives in the profile drawer for detail.
 */
export interface ColumnSparklineProps {
  /** Rows (any subset; we only read `column` from each). */
  rows: ReadonlyArray<Record<string, unknown>>;
  column: string;
  type: string;
  width?: number;
  height?: number;
  /** Render in a muted color (used as the "previous run" overlay layer). */
  muted?: boolean;
  /** Optional precomputed bins, used when the backend already produced them. */
  bins?: ReadonlyArray<{ key: string | number; count: number }>;
}

const NUMERIC_TYPES = new Set([
  "integer",
  "double",
  "index",
  "scientific",
  "percentage",
  "currency",
  "bignum",
]);
const TEMPORAL_TYPES = new Set(["date", "datetime"]);

export function ColumnSparkline({
  rows,
  column,
  type,
  width = 80,
  height = 16,
  muted = false,
  bins,
}: ColumnSparklineProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const computedBins = useMemo(() => {
    if (bins) return bins;
    return computeBins(rows, column, type);
  }, [rows, column, type, bins]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || computedBins.length === 0) return;
    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const max = computedBins.reduce((m, b) => Math.max(m, b.count), 1);
    const barW = width / computedBins.length;
    const inset = barW > 4 ? 1 : 0.5;
    const fill = muted
      ? "rgba(115, 115, 115, 0.35)"
      : "rgb(16 185 129)"; // emerald-500
    ctx.fillStyle = fill;

    for (let i = 0; i < computedBins.length; i++) {
      const h = Math.max(1, (computedBins[i].count / max) * (height - 1));
      const x = i * barW + inset;
      const y = height - h;
      ctx.fillRect(x, y, Math.max(1, barW - inset * 2), h);
    }
  }, [computedBins, width, height, muted]);

  if (computedBins.length === 0) {
    return (
      <div
        className="text-[9px] text-muted-foreground/60 leading-none"
        style={{ width, height }}
        aria-hidden
      />
    );
  }

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height }}
      className="block"
      aria-label={`Distribution of ${column}`}
      role="img"
    />
  );
}

function computeBins(
  rows: ReadonlyArray<Record<string, unknown>>,
  column: string,
  type: string,
): Array<{ key: string | number; count: number }> {
  if (rows.length === 0) return [];

  if (NUMERIC_TYPES.has(type)) {
    return numericBins(rows, column);
  }
  if (TEMPORAL_TYPES.has(type)) {
    return temporalBins(rows, column);
  }
  return categoricalBins(rows, column);
}

function numericBins(
  rows: ReadonlyArray<Record<string, unknown>>,
  column: string,
  binCount = 16,
): Array<{ key: number; count: number }> {
  let lo = Infinity;
  let hi = -Infinity;
  const values: number[] = [];
  for (const r of rows) {
    const v = r[column];
    const n = typeof v === "number" ? v : typeof v === "string" ? parseFloat(v) : NaN;
    if (!Number.isFinite(n)) continue;
    values.push(n);
    if (n < lo) lo = n;
    if (n > hi) hi = n;
  }
  if (values.length === 0 || hi === lo) return [];

  const width = (hi - lo) / binCount;
  const bins = new Array<{ key: number; count: number }>(binCount);
  for (let i = 0; i < binCount; i++) {
    bins[i] = { key: lo + i * width, count: 0 };
  }
  for (const v of values) {
    let idx = Math.floor((v - lo) / width);
    if (idx >= binCount) idx = binCount - 1;
    if (idx < 0) idx = 0;
    bins[idx].count++;
  }
  return bins;
}

function temporalBins(
  rows: ReadonlyArray<Record<string, unknown>>,
  column: string,
): Array<{ key: number; count: number }> {
  const numericRows: Array<Record<string, unknown>> = [];
  for (const r of rows) {
    const v = r[column];
    const t = v instanceof Date ? v.getTime() : typeof v === "string" ? Date.parse(v) : NaN;
    if (Number.isFinite(t)) {
      numericRows.push({ [column]: t });
    }
  }
  return numericBins(numericRows, column, 16) as Array<{ key: number; count: number }>;
}

function categoricalBins(
  rows: ReadonlyArray<Record<string, unknown>>,
  column: string,
  topK = 10,
): Array<{ key: string; count: number }> {
  const counts = new Map<string, number>();
  for (const r of rows) {
    const v = r[column];
    if (v == null) continue;
    const k = typeof v === "string" ? v : String(v);
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, topK);
  return sorted.map(([key, count]) => ({ key, count }));
}

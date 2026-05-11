"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import * as Plot from "@observablehq/plot";
import { fmtInt } from "@/lib/format-number";

// Locale-pinned float formatter. Same reasoning as fmtInt — `.toLocaleString(undefined, …)`
// uses the user's browser locale and disagrees with the SSR output. Pinning
// to en-US keeps the formatted text deterministic across server + client.
const _fmt4 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });

interface ColumnLite {
  name: string;
  type: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  columnName: string | null;
  columnType?: string;
  /** Physical SQL storage type (DECIMAL(18,4), HUGEINT, UUID, …). When
   *  provided, the drawer shows it alongside the logical type so the user
   *  knows the on-disk representation behind a meta-type. */
  columnStorage?: string | null;
  /** Rows currently visible in the grid (in-memory sample). */
  rows: Array<Record<string, unknown>>;
  /** All columns in the data (so the drawer can show position info). */
  columns: ColumnLite[];
  /** Optional: existing per-column annotation + a save callback. */
  annotation?: string;
  onSaveAnnotation?: (column: string, text: string) => Promise<void> | void;
  /** Phase-A-pro #4 — quick-filter callbacks. Click a top-N value to
   *  filter rows EQ that value; click a histogram bar to filter rows
   *  in that numeric range. Both are optional — when absent, the
   *  drawer renders the same content but as read-only display. */
  onValueFilter?: (column: string, value: unknown, mode: "eq" | "neq") => void;
  onRangeFilter?: (column: string, low: number, high: number) => void;
  /** NaN-origin sidecar for this step (same shape as LiveGrid's prop).
   *  Used to render a secondary "of which X were conversion failures"
   *  line below the Nulls stat on the producing step's output. Empty
   *  / undefined on every other step (the sidecar is one-step-only).
   *  See internal/proposals/NULL_AND_NAN_DISPLAY.md. */
  nanOrigins?: Array<{
    column: string;
    cause: "cast_failure" | "arithmetic_nan" | "arithmetic_inf";
    count: number;
    row_indices: number[];
    truncated: boolean;
    source_column?: string;
  }>;
}

const TYPE_EMOJI: Record<string, string> = {
  integer: "🔢", double: "🔢", string: "🅰️", date: "📅",
  datetime: "📅", boolean: "☑️", nested: "🧱",
};

function logical(t: string): string {
  const m = (t || "").toLowerCase();
  if (m.startsWith("int") || m === "bigint") return "integer";
  if (m === "double" || m === "float" || m.includes("decimal") || m.startsWith("float")) return "double";
  if (m.startsWith("bool")) return "boolean";
  if (m === "date") return "date";
  if (m.startsWith("timestamp") || m === "datetime") return "datetime";
  return "string";
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? fmtInt(v) : _fmt4.format(v);
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

export function ProfileDrawer({
  open, onClose, columnName, columnType, columnStorage, rows, columns, annotation, onSaveAnnotation,
  onValueFilter, onRangeFilter, nanOrigins,
}: Props) {
  const [draftNote, setDraftNote] = useState<string>("");
  const [savingNote, setSavingNote] = useState(false);
  // Reset the draft whenever a different column or annotation is loaded.
  useEffect(() => {
    setDraftNote(annotation ?? "");
  }, [columnName, annotation]);
  const chartRef = useRef<HTMLDivElement>(null);

  const profile = useMemo(() => {
    if (!columnName) return null;
    const t = logical(columnType ?? "string");
    const vals = rows.map((r) => r[columnName]);
    const total = vals.length;
    const nonNull = vals.filter((v) => v !== null && v !== undefined);
    const nullCount = total - nonNull.length;

    const stats: Record<string, unknown> = {
      type: t,
      total,
      nullCount,
      nullPct: total ? nullCount / total : 0,
    };

    if (t === "integer" || t === "double") {
      const nums = nonNull
        .map((v) => Number(v))
        .filter((n) => Number.isFinite(n));
      if (nums.length > 0) {
        const sorted = [...nums].sort((a, b) => a - b);
        const n = sorted.length;
        const pct = (q: number) => sorted[Math.min(n - 1, Math.floor(q * n))];
        stats.min = sorted[0];
        stats.max = sorted[n - 1];
        const mean = nums.reduce((a, b) => a + b, 0) / n;
        stats.mean = mean;
        stats.median = pct(0.5);
        stats.p25 = pct(0.25);
        stats.p75 = pct(0.75);
        stats.p90 = pct(0.9);
        stats.p95 = pct(0.95);
        // Standard deviation + outliers (>3σ from mean) — plain
        // textbook stats, no patent risk.
        const variance = nums.reduce((s, v) => s + (v - mean) ** 2, 0) / n;
        const stddev = Math.sqrt(variance);
        stats.stddev = stddev;
        const lowOutlier = mean - 3 * stddev;
        const highOutlier = mean + 3 * stddev;
        stats.outliers = nums.filter((v) => v < lowOutlier || v > highOutlier).length;
        stats.outlierLow = lowOutlier;
        stats.outlierHigh = highOutlier;
      }
    }

    // Top values (works for any type that JSON-stringifies)
    const counts = new Map<string, { count: number; raw: unknown }>();
    for (const v of nonNull) {
      const key = typeof v === "string" ? v : JSON.stringify(v);
      const cur = counts.get(key);
      if (cur) cur.count++;
      else counts.set(key, { count: 1, raw: v });
    }
    const topValues = [...counts.entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 12)
      .map(([k, v]) => ({ value: v.raw, count: v.count, key: k }));
    const distinct = counts.size;
    stats.distinct = distinct;
    stats.topValues = topValues;
    // Phase-A-pro #4 — "suspicious" heuristics. These are NOT
    // proprietary detection algorithms (Trifacta has patents around
    // those); we surface only obvious-from-stats observations a user
    // could read off the numbers themselves. Each heuristic has a
    // single fixed threshold, so it's a pure boolean derivation, not
    // a learned model.
    const warnings: Array<{ kind: string; label: string; emoji: string }> = [];
    if (stats.nullPct as number >= 0.5 && stats.total as number > 0) {
      warnings.push({ kind: "high-nulls", label: "Over 50% NULLs", emoji: "⚠️" });
    } else if (stats.nullPct as number >= 0.05) {
      warnings.push({ kind: "some-nulls", label: `${((stats.nullPct as number) * 100).toFixed(0)}% NULLs`, emoji: "⚠️" });
    }
    if (stats.distinct === 1 && (stats.total as number) > 1) {
      warnings.push({ kind: "single-value", label: "Single distinct value (constant)", emoji: "🟰" });
    }
    if (typeof stats.distinct === "number" && stats.distinct === stats.total && (stats.total as number) > 1) {
      warnings.push({ kind: "all-distinct", label: "Every row has a unique value (likely a key)", emoji: "🔑" });
    }
    if (typeof stats.outliers === "number" && stats.outliers > 0) {
      warnings.push({
        kind: "outliers",
        label: `${stats.outliers} outlier${stats.outliers === 1 ? "" : "s"} (|z| > 3)`,
        emoji: "🎯",
      });
    }
    stats.warnings = warnings;

    return stats as {
      type: string; total: number; nullCount: number; nullPct: number;
      min?: number; max?: number; mean?: number; median?: number;
      p25?: number; p75?: number; p90?: number; p95?: number;
      stddev?: number; outliers?: number;
      outlierLow?: number; outlierHigh?: number;
      distinct: number;
      topValues: Array<{ value: unknown; count: number; key: string }>;
      warnings: Array<{ kind: string; label: string; emoji: string }>;
    };
  }, [columnName, columnType, rows]);

  useEffect(() => {
    if (!chartRef.current || !profile || !columnName) return;
    chartRef.current.innerHTML = "";
    const t = logical(columnType ?? "string");
    let plot: HTMLElement | SVGElement | undefined;
    try {
      if ((t === "integer" || t === "double") && profile.min != null && profile.max != null) {
        const nums = rows
          .map((r) => Number(r[columnName]))
          .filter((n) => Number.isFinite(n));
        // Hand-bin into 20 equal-width buckets so we don't fight Plot's binX types.
        const lo = profile.min!;
        const hi = profile.max!;
        const binCount = 20;
        const width = (hi - lo) / binCount || 1;
        const bins = new Array(binCount).fill(0).map((_, i) => ({
          x0: lo + i * width,
          x1: lo + (i + 1) * width,
          n: 0,
        }));
        for (const n of nums) {
          const idx = Math.min(binCount - 1, Math.max(0, Math.floor((n - lo) / width)));
          bins[idx].n++;
        }
        plot = Plot.plot({
          width: 320, height: 110, marginLeft: 28, marginBottom: 22,
          y: { label: null, tickFormat: "s" },
          x: { label: null },
          marks: [
            Plot.rectY(bins, {
              x1: "x0", x2: "x1", y: "n",
              fill: "currentColor", fillOpacity: 0.65,
              // Phase-A-pro #4: clicking a histogram bar filters the
              // grid to rows with values inside that bar's range.
              // Pointer-style cursor signals the affordance.
              ...(onRangeFilter ? {
                cursor: "pointer",
                title: (d: { x0: number; x1: number; n: number }) =>
                  `${d.n} row${d.n === 1 ? "" : "s"} in [${d.x0.toFixed(2)}, ${d.x1.toFixed(2)}] — click to filter`,
              } : {}),
            }),
          ],
          style: { background: "transparent" },
        });
        if (onRangeFilter && plot) {
          // Plot's bars don't expose per-bar click handlers cleanly, so
          // hook a delegated listener on the plot's <svg> that maps the
          // cursor X back to a bin and fires the range filter.
          //
          // Tightened for QA #3: the previous version fired on ANY click
          // inside the SVG — including y-axis labels, the area below the
          // bars, and clicks on whitespace to the right of the plot.
          // Now we (1) walk up from the click target to find the closest
          // <rect> (Plot renders bars as rect elements); if there's no
          // rect ancestor inside the plot's bar group, the click was on
          // chrome (axes / labels) and we ignore it. (2) Constrain the
          // x-pct to the plot area — Plot's left margin is 28 (matches
          // the manual offset above) and right margin is small enough to
          // ignore without explicit subtraction; clamping fixes both.
          plot.addEventListener("click", (ev: Event) => {
            const e = ev as MouseEvent;
            const target = e.target as Element | null;
            // Only fire when the click landed on or inside a bar rect.
            if (!target || !target.closest("g[aria-label='bar'] rect, g[aria-label='rect'] rect")) {
              // Plot doesn't always set aria-label on the bar group, so
              // also accept any direct rect descendant whose computed
              // height is non-zero — that's a bar, not chrome.
              const rectEl = target?.closest("rect");
              if (!rectEl) return;
              const r = rectEl.getBoundingClientRect();
              if (r.width < 1 || r.height < 1) return;
            }
            const svgEl = plot as SVGSVGElement;
            const rect = svgEl.getBoundingClientRect();
            const plotLeft = 28;       // matches Plot's marginLeft below
            const plotRight = 8;       // approx Plot default marginRight
            const usable = rect.width - plotLeft - plotRight;
            if (usable <= 0) return;
            const xRel = e.clientX - rect.left - plotLeft;
            if (xRel < 0 || xRel > usable) return;  // outside the plot area
            const xPct = xRel / usable;
            const idx = Math.min(binCount - 1, Math.max(0, Math.floor(xPct * binCount)));
            const b = bins[idx];
            if (b && columnName) onRangeFilter(columnName, b.x0, b.x1);
          });
        }
      } else {
        const data = profile.topValues.map((v) => ({ k: v.key.slice(0, 28), n: v.count }));
        plot = Plot.plot({
          width: 320, height: Math.max(110, data.length * 18 + 24), marginLeft: 110, marginBottom: 22,
          y: { label: null, domain: data.map((d) => d.k) },
          x: { label: null },
          marks: [Plot.barX(data, { x: "n", y: "k", fill: "currentColor", fillOpacity: 0.65 })],
          style: { background: "transparent" },
        });
      }
    } catch (e) {
      console.warn("profile chart failed", e);
    }
    if (plot) chartRef.current.appendChild(plot);
  }, [profile, columnName, columnType, rows]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const fn = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && columnName && profile && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/30"
          />
          <motion.aside
            key="drawer"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 36 }}
            className="fixed top-0 right-0 bottom-0 z-50 w-[380px] bg-card border-l border-border shadow-2xl flex flex-col"
          >
            <header className="px-4 py-3 border-b border-border flex items-center gap-3 shrink-0">
              <span className="text-2xl" aria-hidden>{TYPE_EMOJI[logical(columnType ?? "")] ?? "❔"}</span>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Profile</p>
                <p className="font-medium truncate" title={columnName}>{columnName}</p>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="text-muted-foreground hover:text-foreground"
              >
                ✕
              </button>
            </header>

            <div className="overflow-y-auto flex-1 p-4 space-y-4">
              {/* Type + position */}
              <section className="text-xs">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Type</p>
                <p className="font-mono">{columnType}</p>
                {columnStorage && (
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Stored as <span className="font-mono text-foreground/80">{columnStorage}</span>
                  </p>
                )}
                <p className="text-muted-foreground mt-1">
                  Position {columns.findIndex((c) => c.name === columnName) + 1} of {columns.length}
                </p>
              </section>

              {/* Phase-A-pro #4 — suspicious-heuristic warnings.
                  Renders at the top of the drawer so the user lands
                  on the most actionable signal first. */}
              {profile.warnings.length > 0 && (
                <section className="space-y-1">
                  {profile.warnings.map((w) => (
                    <div
                      key={w.kind}
                      className="text-[11px] flex items-center gap-2 px-2.5 py-1.5 rounded border border-amber-300/40 bg-amber-50/60 dark:bg-amber-950/30 dark:border-amber-900/60 text-amber-900 dark:text-amber-200"
                    >
                      <span aria-hidden>{w.emoji}</span>
                      <span>{w.label}</span>
                    </div>
                  ))}
                </section>
              )}

              {/* Stats grid */}
              <section className="grid grid-cols-2 gap-2 text-xs tabular-nums">
                <Stat label="Rows in sample" value={fmtInt(profile.total)} />
                <Stat label="Distinct" value={fmtInt(profile.distinct)} />
                <Stat
                  label="Nulls"
                  value={`${fmtInt(profile.nullCount)} (${(profile.nullPct * 100).toFixed(profile.nullPct < 0.01 ? 2 : 1)}%)`}
                  warn={profile.nullPct >= 0.05}
                />
                {(() => {
                  // Per-column conversion-failure count from the
                  // step's NaN-origin sidecar. Surfaces ONLY on the
                  // producing step (the sidecar is one-step-only).
                  // See internal/proposals/NULL_AND_NAN_DISPLAY.md.
                  const entries = (nanOrigins ?? []).filter(
                    (o) => o.column === columnName,
                  );
                  if (entries.length === 0) return null;
                  const totalFailures = entries.reduce(
                    (sum, e) => sum + e.count, 0,
                  );
                  const causeLabel = entries.some((e) => e.cause === "cast_failure")
                    ? "conversion failures"
                    : "computation NaN/±Inf";
                  return (
                    <div
                      className="col-span-2 -mt-1 ml-1 text-[11px] text-orange-700 dark:text-orange-300"
                      title="These nulls were produced by THIS step. The next step sees plain NULL."
                    >
                      <span aria-hidden>⚠</span>{" "}
                      of which {fmtInt(totalFailures)} {causeLabel} in this step
                    </div>
                  );
                })()}
                {profile.mean != null && (
                  <Stat label="Mean" value={fmt(profile.mean)} />
                )}
                {profile.median != null && (
                  <Stat label="Median" value={fmt(profile.median)} />
                )}
                {profile.min != null && (
                  <Stat label="Min" value={fmt(profile.min)} />
                )}
                {profile.max != null && (
                  <Stat label="Max" value={fmt(profile.max)} />
                )}
                {profile.stddev != null && (
                  <Stat label="Std dev" value={fmt(profile.stddev)} />
                )}
              </section>

              {/* Percentile breakdown — the columns most data analysts
                  reach for on first inspection. Hidden for non-numeric. */}
              {profile.p25 != null && (
                <section>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">
                    Percentiles
                  </p>
                  <div className="grid grid-cols-5 gap-1 text-[11px] tabular-nums">
                    {(["p25", "median", "p75", "p90", "p95"] as const).map((k) => {
                      const labelMap: Record<string, string> = {
                        p25: "P25", median: "P50", p75: "P75", p90: "P90", p95: "P95",
                      };
                      const v = profile[k as keyof typeof profile] as number | undefined;
                      return (
                        <div key={k} className="rounded border border-border bg-muted/20 px-1.5 py-1">
                          <div className="text-[9px] uppercase tracking-wider text-muted-foreground">
                            {labelMap[k]}
                          </div>
                          <div className="font-medium">{v != null ? fmt(v) : "—"}</div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Chart */}
              <section>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  {(profile.type === "integer" || profile.type === "double") ? "📊 Distribution" : "📊 Top values"}
                </p>
                <div ref={chartRef} className="text-foreground/85" />
              </section>

              {/* Top-K table — each row is clickable to filter the
                  grid by that value (Phase-A-pro #4). When the parent
                  doesn't pass `onValueFilter` (e.g. the dataset
                  inspector), values stay read-only. */}
              {profile.topValues.length > 0 && (
                <section>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 flex items-center justify-between">
                    <span>Top {profile.topValues.length} value{profile.topValues.length === 1 ? "" : "s"}</span>
                    {onValueFilter && <span className="normal-case font-normal tracking-normal text-muted-foreground/70">click to filter</span>}
                  </p>
                  <ul className="space-y-0.5 text-xs tabular-nums">
                    {profile.topValues.map((v) => (
                      <li key={v.key} className="flex items-center gap-2">
                        {onValueFilter ? (
                          <button
                            type="button"
                            onClick={() => onValueFilter(columnName!, v.value, "eq")}
                            title={`Filter rows where ${columnName} = ${v.key.slice(0, 60)}`}
                            className="truncate flex-1 text-left hover:underline underline-offset-2 hover:text-foreground"
                          >
                            {v.key || "—"}
                          </button>
                        ) : (
                          <span className="truncate flex-1" title={v.key}>{v.key || "—"}</span>
                        )}
                        <span className="text-muted-foreground">{fmtInt(v.count)}</span>
                        <span className="text-[10px] text-muted-foreground/70 w-10 text-right">
                          {((v.count / profile.total) * 100).toFixed(1)}%
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Annotation editor — opt-in via onSaveAnnotation */}
              {onSaveAnnotation && (
                <section>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                    📝 Annotation
                  </p>
                  <textarea
                    value={draftNote}
                    onChange={(e) => setDraftNote(e.target.value)}
                    placeholder={
                      "What does this column mean? Units? Caveats?\n(e.g. 'amount is in cents, not dollars')"
                    }
                    rows={3}
                    className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring/40"
                  />
                  <div className="flex items-center justify-between mt-1.5">
                    <p className="text-[10px] text-muted-foreground/70">
                      Saves to the dataset, visible in any pipeline that uses it.
                    </p>
                    <button
                      type="button"
                      disabled={savingNote || draftNote === (annotation ?? "")}
                      onClick={async () => {
                        if (!columnName) return;
                        setSavingNote(true);
                        try {
                          await onSaveAnnotation(columnName, draftNote);
                        } finally {
                          setSavingNote(false);
                        }
                      }}
                      className="text-[11px] px-2 py-1 rounded-md bg-foreground text-background disabled:opacity-40 transition-opacity"
                    >
                      {savingNote ? "saving…" : "save"}
                    </button>
                  </div>
                </section>
              )}
            </div>

            <footer className="px-4 py-2 border-t border-border text-[10px] text-muted-foreground shrink-0">
              Stats computed from the in-grid sample.
            </footer>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-card/40 p-2">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground/70">{label}</p>
      <p className={["font-medium", warn ? "text-amber-600 dark:text-amber-400" : ""].join(" ")}>{value}</p>
    </div>
  );
}

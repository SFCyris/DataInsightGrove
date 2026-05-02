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
  /** Rows currently visible in the grid (in-memory sample). */
  rows: Array<Record<string, unknown>>;
  /** All columns in the data (so the drawer can show position info). */
  columns: ColumnLite[];
  /** Optional: existing per-column annotation + a save callback. */
  annotation?: string;
  onSaveAnnotation?: (column: string, text: string) => Promise<void> | void;
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
  open, onClose, columnName, columnType, rows, columns, annotation, onSaveAnnotation,
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
        stats.min = sorted[0];
        stats.max = sorted[sorted.length - 1];
        stats.mean = nums.reduce((a, b) => a + b, 0) / nums.length;
        stats.median = sorted[Math.floor(sorted.length / 2)];
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
    return stats as {
      type: string; total: number; nullCount: number; nullPct: number;
      min?: number; max?: number; mean?: number; median?: number;
      distinct: number;
      topValues: Array<{ value: unknown; count: number; key: string }>;
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
            }),
          ],
          style: { background: "transparent" },
        });
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
                <p className="text-muted-foreground mt-1">
                  Position {columns.findIndex((c) => c.name === columnName) + 1} of {columns.length}
                </p>
              </section>

              {/* Stats grid */}
              <section className="grid grid-cols-2 gap-2 text-xs tabular-nums">
                <Stat label="Rows in sample" value={fmtInt(profile.total)} />
                <Stat label="Distinct" value={fmtInt(profile.distinct)} />
                <Stat
                  label="Nulls"
                  value={`${fmtInt(profile.nullCount)} (${(profile.nullPct * 100).toFixed(profile.nullPct < 0.01 ? 2 : 1)}%)`}
                  warn={profile.nullPct >= 0.05}
                />
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
              </section>

              {/* Chart */}
              <section>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  {(profile.type === "integer" || profile.type === "double") ? "📊 Distribution" : "📊 Top values"}
                </p>
                <div ref={chartRef} className="text-foreground/85" />
              </section>

              {/* Top-K table */}
              {profile.topValues.length > 0 && (
                <section>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                    Top {profile.topValues.length} value{profile.topValues.length === 1 ? "" : "s"}
                  </p>
                  <ul className="space-y-0.5 text-xs tabular-nums">
                    {profile.topValues.map((v) => (
                      <li key={v.key} className="flex items-center gap-2">
                        <span className="truncate flex-1" title={v.key}>{v.key || "—"}</span>
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

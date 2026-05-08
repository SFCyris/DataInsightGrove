"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/button";
import {
  METHODS_NEEDING_COLUMN,
  METHODS_NEEDING_TIME_COLUMN,
  SAMPLING_METHODS,
  type SamplingConfig,
  type SamplingMethod,
  type TimeBucket,
} from "@/lib/sampling";

/**
 * 🧪 Sampling — popup that lets the user pick how the editor preview
 * draws sample rows from the pipeline output. Stored on the pipeline
 * document's `metadata.sampling` so it travels with the pipeline.
 *
 * Methods are grouped into three tiers so the universal four are seen
 * first; the distribution-aware and statistical methods sit below
 * with subdued tier headers — discoverable without overwhelming a
 * first-time user. Each tier:
 *   - universal      head / tail / random / systematic
 *   - distribution   stratified / per_group / time_bucket
 *   - statistical    weighted / bootstrap
 *
 * Per-method controls render conditionally:
 *   - stratified / per_group / weighted   ← column picker
 *   - time_bucket                          ← time column + granularity
 *   - random / stratified / per_group / time_bucket  ← optional seed
 *   - systematic                           ← every-Nth instead of size
 *
 * "Size" is overloaded — it means total-rows for most methods,
 * per-group/per-bucket-rows for `per_group` / `time_bucket`. Helper
 * text under the input makes that distinction explicit so users
 * aren't surprised when "size = 10" produces 10 × N_groups rows.
 */
interface ColumnInfo {
  name: string;
  type: string;
}

interface Props {
  open: boolean;
  value: SamplingConfig;
  onChange: (next: SamplingConfig) => void;
  onClose: () => void;
  /** Columns visible somewhere in the pipeline — used to populate
   *  per-method pickers. Typically the first dataset's columns; the
   *  page computes them from the schemas index. */
  availableColumns?: ColumnInfo[];
}

const TIER_LABELS = {
  universal: "Universal",
  distribution: "Distribution-aware",
  statistical: "Statistical",
} as const;

const TIER_BLURBS = {
  universal: "No column needed — start here.",
  distribution: "Use a column to keep imbalanced classes / per-group / time buckets representative.",
  statistical: "For statistical workflows + revenue-weighted previews.",
} as const;

const BUCKET_LABELS: Record<TimeBucket, string> = {
  hour: "Hour", day: "Day", week: "Week",
  month: "Month", quarter: "Quarter", year: "Year",
};

/** Column-type heuristics to pick smart defaults. The picker doesn't
 *  enforce these — users can override — but the default reduces the
 *  number of clicks for the typical case (low-cardinality categorical
 *  for stratified, time/date for time_bucket, numeric for weighted). */
function pickSmartColumn(
  cols: ColumnInfo[],
  method: SamplingMethod,
): string | undefined {
  if (cols.length === 0) return undefined;
  const isNumeric = (t: string) =>
    /int|float|double|decimal|number|currency|percentage/i.test(t);
  const isTemporal = (t: string) =>
    /date|time|timestamp|datetime/i.test(t);
  const isLowCardish = (t: string) =>
    /string|str|category|enum|bool/i.test(t);

  if (method === "stratified" || method === "per_group") {
    return cols.find((c) => isLowCardish(c.type))?.name ?? cols[0]?.name;
  }
  if (method === "weighted") {
    return cols.find((c) => isNumeric(c.type))?.name;
  }
  return cols[0]?.name;
}

function pickSmartTimeColumn(cols: ColumnInfo[]): string | undefined {
  return cols.find((c) => /date|time|timestamp|datetime/i.test(c.type))?.name;
}

export function SamplingDialog({
  open, value, onChange, onClose, availableColumns = [],
}: Props) {
  const [draft, setDraft] = useState<SamplingConfig>(value);

  // Reset the draft to the persisted value whenever the dialog opens.
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  // Group methods by tier; preserves order within a tier.
  const tieredMethods = useMemo(() => {
    const out: Record<string, typeof SAMPLING_METHODS> = {
      universal: [], distribution: [], statistical: [],
    };
    for (const m of SAMPLING_METHODS) out[m.tier].push(m);
    return out;
  }, []);

  // Per-method validity. Apply is disabled when the chosen method
  // needs a column / time column and the draft hasn't supplied one.
  const validation = useMemo(() => {
    const needsColumn = METHODS_NEEDING_COLUMN.has(draft.method);
    const needsTimeColumn = METHODS_NEEDING_TIME_COLUMN.has(draft.method);
    if (needsColumn && !draft.column) {
      return {
        ok: false,
        message: "Pick a column for this method.",
      };
    }
    if (needsTimeColumn && !draft.timeColumn) {
      return {
        ok: false,
        message: "Pick a timestamp column for this method.",
      };
    }
    return { ok: true, message: "" };
  }, [draft]);

  // Update method + auto-fill smart defaults so the user doesn't have
  // to touch the column picker for the typical case. Existing values
  // are preserved when they still apply (e.g. switching stratified→
  // per_group keeps the same `column`).
  const setMethod = (next: SamplingMethod) => {
    setDraft((d) => {
      const updates: Partial<SamplingConfig> = { method: next };
      if (METHODS_NEEDING_COLUMN.has(next) && !d.column) {
        updates.column = pickSmartColumn(availableColumns, next);
      }
      if (METHODS_NEEDING_TIME_COLUMN.has(next) && !d.timeColumn) {
        updates.timeColumn = pickSmartTimeColumn(availableColumns);
        updates.bucket = updates.bucket ?? "day";
      }
      return { ...d, ...updates };
    });
  };

  const apply = () => {
    if (!validation.ok) return;
    onChange(draft);
    onClose();
  };

  const sizeLabel =
    draft.method === "per_group" ? "Rows per group"
    : draft.method === "time_bucket" ? "Rows per bucket"
    : "Sample size (rows)";

  const sizeHint =
    draft.method === "per_group"
      ? `Total result ≈ ${draft.size} × distinct values of ${draft.column ?? "column"}.`
      : draft.method === "time_bucket"
      ? `Total result ≈ ${draft.size} × number of ${draft.bucket ?? "day"} buckets in the data.`
      : "";

  // Methods that accept a seed for reproducibility. weighted +
  // bootstrap have a documented compromise (seed not threaded inline)
  // so they're left out — see lib/sampling.ts comments.
  const showSeed = (
    draft.method === "random"
    || draft.method === "stratified"
    || draft.method === "per_group"
    || draft.method === "time_bucket"
  );

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="sampling-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/30"
          />
          <motion.div
            key="sampling-dialog"
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 360, damping: 32 }}
            role="dialog"
            aria-label="Sampling settings"
            className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 w-[520px] max-h-[88vh] overflow-y-auto rounded-xl border border-border bg-card shadow-2xl p-5"
          >
            <header className="flex items-center gap-3 mb-4">
              <span className="text-2xl select-none" aria-hidden>🧪</span>
              <div className="flex-1">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Pipeline preview
                </p>
                <h2 className="text-base font-semibold leading-tight">
                  Sampling method
                </h2>
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

            <p className="text-[11px] text-muted-foreground mb-4 leading-relaxed">
              Controls how the editor preview draws rows from the pipeline
              output. Saved with the pipeline so each flow can use a
              different method. Doesn&apos;t affect full-data backend runs.
            </p>

            <div className="space-y-3">
              {(["universal", "distribution", "statistical"] as const).map((tier) => (
                <div key={tier}>
                  <div className="flex items-baseline gap-2 mb-1.5">
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                      {TIER_LABELS[tier]}
                    </p>
                    <p className="text-[10px] text-muted-foreground/70 italic">
                      {TIER_BLURBS[tier]}
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    {tieredMethods[tier].map((m) => (
                      <label
                        key={m.id}
                        className={[
                          "flex items-start gap-3 rounded-lg border px-3 py-2 cursor-pointer transition-colors",
                          draft.method === m.id
                            ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20"
                            : "border-border hover:border-foreground/30",
                        ].join(" ")}
                      >
                        <input
                          type="radio"
                          name="sampling-method"
                          checked={draft.method === m.id}
                          onChange={() => setMethod(m.id as SamplingMethod)}
                          className="mt-1"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium flex items-center gap-1.5">
                            <span aria-hidden>{m.emoji}</span>
                            {m.label}
                          </p>
                          <p className="text-[11px] text-muted-foreground leading-snug mt-0.5">
                            {m.blurb}
                          </p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Method-specific params */}
            <div className="mt-4 space-y-3 border-t border-border/60 pt-4">
              {/* Column picker — stratified / per_group / weighted */}
              {METHODS_NEEDING_COLUMN.has(draft.method) && (
                <div className="grid grid-cols-[1fr_2fr] gap-3 items-center">
                  <label className="text-sm font-medium">
                    {draft.method === "weighted" ? "Weight column" : "Column"}
                  </label>
                  <select
                    value={draft.column ?? ""}
                    onChange={(e) =>
                      setDraft({ ...draft, column: e.target.value || undefined })
                    }
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                  >
                    <option value="">— pick a column —</option>
                    {availableColumns.map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.name}  ·  {c.type}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Time column + bucket granularity — time_bucket */}
              {METHODS_NEEDING_TIME_COLUMN.has(draft.method) && (
                <>
                  <div className="grid grid-cols-[1fr_2fr] gap-3 items-center">
                    <label className="text-sm font-medium">Time column</label>
                    <select
                      value={draft.timeColumn ?? ""}
                      onChange={(e) =>
                        setDraft({ ...draft, timeColumn: e.target.value || undefined })
                      }
                      className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    >
                      <option value="">— pick a timestamp column —</option>
                      {availableColumns.map((c) => (
                        <option key={c.name} value={c.name}>
                          {c.name}  ·  {c.type}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-[1fr_2fr] gap-3 items-center">
                    <label className="text-sm font-medium">Bucket size</label>
                    <select
                      value={draft.bucket ?? "day"}
                      onChange={(e) =>
                        setDraft({ ...draft, bucket: e.target.value as TimeBucket })
                      }
                      className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    >
                      {(Object.keys(BUCKET_LABELS) as TimeBucket[]).map((b) => (
                        <option key={b} value={b}>{BUCKET_LABELS[b]}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}

              {/* Size or every-Nth */}
              {draft.method !== "systematic" && (
                <div className="grid grid-cols-[1fr_2fr] gap-3 items-start">
                  <label className="text-sm font-medium">{sizeLabel}</label>
                  <div>
                    <input
                      type="number"
                      min={1}
                      max={10_000_000}
                      value={draft.size}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          size: Math.max(1, Number(e.target.value) || 1),
                        })
                      }
                      className="w-full rounded-md border border-input bg-background px-2 py-1 text-sm font-mono"
                    />
                    {sizeHint && (
                      <p className="text-[10px] text-muted-foreground mt-1 leading-snug">
                        {sizeHint}
                      </p>
                    )}
                  </div>
                </div>
              )}
              {draft.method === "systematic" && (
                <div className="grid grid-cols-[1fr_2fr] gap-3 items-center">
                  <label className="text-sm font-medium">Take every Nth row</label>
                  <input
                    type="number"
                    min={2}
                    max={100_000}
                    value={draft.everyN ?? 10}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        everyN: Math.max(2, Number(e.target.value) || 2),
                      })
                    }
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm font-mono"
                  />
                </div>
              )}

              {/* Optional seed — most methods support it */}
              {showSeed && (
                <div className="grid grid-cols-[1fr_2fr] gap-3 items-center">
                  <label className="text-sm font-medium">Seed (optional)</label>
                  <input
                    type="number"
                    placeholder="leave blank for non-reproducible"
                    value={draft.seed ?? ""}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        seed:
                          e.target.value === ""
                            ? undefined
                            : Math.floor(Number(e.target.value)),
                      })
                    }
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm font-mono"
                  />
                </div>
              )}
            </div>

            {!validation.ok && (
              <p className="mt-3 text-[11px] text-amber-700 dark:text-amber-300 flex items-center gap-1.5">
                <span aria-hidden>⚠</span>
                {validation.message}
              </p>
            )}

            <div className="flex justify-end gap-2 mt-5">
              <Button size="sm" variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button size="sm" onClick={apply} disabled={!validation.ok}>
                💾 Apply
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

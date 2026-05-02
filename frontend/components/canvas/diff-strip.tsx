"use client";

import { motion, AnimatePresence } from "motion/react";

export interface DiffSummary {
  /** columns present after this step but not before */
  addedColumns: string[];
  /** columns present before but not after (e.g. drop_column, select_columns) */
  droppedColumns: string[];
  /** rename mappings detected between consecutive schemas */
  renamedColumns: Array<{ from: string; to: string }>;
  /** rows after / rows before — null if not yet measured */
  rowDelta: number | null;
  rowsBefore: number | null;
  rowsAfter: number | null;
  stepLabel: string;
}

interface Props {
  diff: DiffSummary | null;
}

export function DiffStrip({ diff }: Props) {
  if (!diff) return null;
  const { addedColumns, droppedColumns, renamedColumns, rowDelta, rowsBefore, rowsAfter, stepLabel } = diff;
  const hasContent =
    addedColumns.length > 0 ||
    droppedColumns.length > 0 ||
    renamedColumns.length > 0 ||
    rowDelta !== null;
  if (!hasContent) return null;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={stepLabel}
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ type: "spring", stiffness: 320, damping: 30 }}
        className="px-3 py-1.5 border-b border-border bg-emerald-50/30 dark:bg-emerald-900/10 flex items-center gap-2 text-[11px] flex-wrap shrink-0"
      >
        <span className="text-muted-foreground/80 shrink-0">Δ vs previous:</span>

        {rowDelta !== null && rowDelta !== 0 && (
          <Chip
            tone={rowDelta < 0 ? "red" : "green"}
            label={`${rowDelta > 0 ? "+" : ""}${rowDelta.toLocaleString()} rows`}
            title={`${rowsBefore?.toLocaleString() ?? "?"} → ${rowsAfter?.toLocaleString() ?? "?"}`}
          />
        )}
        {rowDelta === 0 && rowsBefore !== null && (
          <Chip tone="neutral" label={`row count unchanged (${rowsAfter?.toLocaleString()})`} />
        )}

        {addedColumns.map((c) => (
          <Chip key={`+${c}`} tone="green" label={`+ ${c}`} title="new column" />
        ))}
        {droppedColumns.map((c) => (
          <Chip key={`-${c}`} tone="red" label={`− ${c}`} title="dropped" />
        ))}
        {renamedColumns.map((r) => (
          <Chip
            key={`~${r.from}→${r.to}`}
            tone="amber"
            label={`${r.from} → ${r.to}`}
            title="renamed"
          />
        ))}

        <span className="flex-1" />
        <span className="text-muted-foreground/60 shrink-0">applying: {stepLabel}</span>
      </motion.div>
    </AnimatePresence>
  );
}

function Chip({
  tone, label, title,
}: { tone: "green" | "red" | "amber" | "neutral"; label: string; title?: string }) {
  const cls = {
    green: "border-emerald-300/50 bg-emerald-100/60 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200",
    red: "border-red-300/50 bg-red-100/60 text-red-800 dark:bg-red-900/30 dark:text-red-200",
    amber: "border-amber-300/50 bg-amber-100/60 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200",
    neutral: "border-border bg-muted/50 text-muted-foreground",
  }[tone];
  return (
    <span
      title={title}
      className={`px-1.5 py-0.5 rounded-full border text-[10px] tabular-nums whitespace-nowrap ${cls}`}
    >
      {label}
    </span>
  );
}

/** Diff two ordered column lists (from /validate's per-node schemas). */
export function diffColumns(
  prev: string[],
  next: string[],
): {
  addedColumns: string[];
  droppedColumns: string[];
  renamedColumns: Array<{ from: string; to: string }>;
} {
  const prevSet = new Set(prev);
  const nextSet = new Set(next);
  const added = next.filter((c) => !prevSet.has(c));
  const dropped = prev.filter((c) => !nextSet.has(c));

  // Heuristic rename detection: if there's an equal number of added & dropped
  // and the dropped/added pairs are at matching positions in their respective
  // lists, treat them as renames. (Catches the common case of rename_columns
  // step. Doesn't try to be clever — we'd rather miss a rename and call it
  // an add+drop than falsely pair unrelated columns.)
  const renamed: Array<{ from: string; to: string }> = [];
  if (added.length > 0 && added.length === dropped.length) {
    // pair by order (rename_columns preserves position).
    for (let i = 0; i < added.length; i++) {
      renamed.push({ from: dropped[i], to: added[i] });
    }
    return { addedColumns: [], droppedColumns: [], renamedColumns: renamed };
  }
  return { addedColumns: added, droppedColumns: dropped, renamedColumns: [] };
}

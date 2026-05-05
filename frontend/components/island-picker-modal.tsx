"use client";

import { motion, AnimatePresence } from "motion/react";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError, type Dataset } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { fmtInt } from "@/lib/format-number";

/**
 * Island shape produced by `dig.engine.data_islands`. The OpenAPI emits this
 * as `Record<string, unknown>` because the backend types the field as
 * `dict[str, Any]`; we narrow at the consumer so the rest of the component
 * stays strongly typed. Keep in sync with backend/dig/engine/data_islands.py.
 */
interface IslandPreview {
  range_a1: string;
  n_rows: number;
  n_cols: number;
  density: number;
  preview_first_row: Array<string | null>;
}

interface Props {
  /** The just-uploaded dataset in `awaiting_island_pick` status. */
  dataset: Dataset;
  onPicked: (next: Dataset) => void;
  onCancel: () => void;
}

/**
 * Modal that surfaces the detected data islands on an Excel sheet and
 * lets the user pick which one to ingest.
 *
 * Each island shows: Excel A1 range, dimensions, density (filled/total),
 * and a preview of the first row. The user clicks one and we resume
 * ingest via PUT /datasets/{id}/island.
 *
 * Detection logic lives backend-side in dig.engine.data_islands — uses
 * blank rows + columns as cuts. Two-step UX: pick a sheet (if multi-sheet),
 * then pick an island (if multi-island). One-island sheets skip both.
 */
export function IslandPickerModal({ dataset, onPicked, onCancel }: Props) {
  const islands = (dataset.availableIslands ?? []) as unknown as IslandPreview[];
  const [picked, setPicked] = useState<string>(islands[0]?.range_a1 ?? "");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async () => {
    if (!picked) return;
    setSubmitting(true);
    try {
      const next = await api.pickIsland(dataset.id, picked);
      if (next.status === "failed") {
        toast.error(`Ingest failed: ${next.error ?? "unknown"}`);
      } else {
        toast.success(`📐 Imported island ${picked} (${next.rowCount?.toLocaleString() ?? "?"} rows)`);
      }
      onPicked(next);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        key="island-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onCancel}
      />
      <motion.div
        key="island-modal"
        initial={{ opacity: 0, y: 8, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 360, damping: 28 }}
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[640px] max-w-[92vw] max-h-[88vh] bg-card border border-border rounded-lg shadow-2xl p-5 space-y-4 flex flex-col"
        role="dialog"
        aria-label="Pick data island"
      >
        <header className="flex items-center gap-2 shrink-0">
          <span className="text-2xl" aria-hidden>📐</span>
          <div className="flex-1 min-w-0">
            <h2 className="font-medium truncate">Pick a data island</h2>
            <p className="text-[11px] text-muted-foreground truncate">
              {dataset.name}{dataset.selectedSheet ? ` · sheet "${dataset.selectedSheet}"` : ""} · {islands.length} disjoint tables found
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <p className="text-xs text-muted-foreground shrink-0">
          The sheet has multiple disjoint tables. Pick which rectangle of cells
          to import — DIG ingests just that range. Each island's preview shows
          the first row so you can tell them apart.
        </p>

        <div className="flex-1 overflow-y-auto rounded-md border border-border/60 divide-y divide-border/40 min-h-0">
          {islands.map((isle) => (
            <label
              key={isle.range_a1}
              className={[
                "flex items-start gap-3 px-3 py-3 cursor-pointer text-sm transition-colors",
                picked === isle.range_a1 ? "bg-emerald-50 dark:bg-emerald-900/20" : "hover:bg-muted/40",
              ].join(" ")}
            >
              <input
                type="radio"
                name="island"
                value={isle.range_a1}
                checked={picked === isle.range_a1}
                onChange={() => setPicked(isle.range_a1)}
                className="mt-1 shrink-0"
              />
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <code className="font-mono text-foreground text-[12px] px-1.5 py-0.5 rounded bg-background border border-border">
                    {isle.range_a1}
                  </code>
                  <span className="text-[11px] text-muted-foreground tabular-nums">
                    {fmtInt(isle.n_rows)} × {isle.n_cols} cells
                  </span>
                  {isle.density < 1.0 && (
                    <span className="text-[10px] text-muted-foreground">
                      · {Math.round(isle.density * 100)}% filled
                    </span>
                  )}
                </div>
                {isle.preview_first_row.some((c) => c) && (
                  <div className="flex flex-wrap gap-1 text-[11px] text-muted-foreground">
                    <span className="text-[9px] uppercase tracking-widest text-muted-foreground/70 mr-1">first row:</span>
                    {isle.preview_first_row.map((cell, i) => (
                      <span
                        key={i}
                        className="font-mono px-1 py-0.5 rounded bg-muted/40 truncate max-w-[120px]"
                      >
                        {cell ?? <span className="opacity-40 italic">·</span>}
                      </span>
                    ))}
                    {isle.n_cols > isle.preview_first_row.length && (
                      <span className="text-[10px] opacity-60">+{isle.n_cols - isle.preview_first_row.length} more cols</span>
                    )}
                  </div>
                )}
              </div>
            </label>
          ))}
        </div>

        <footer className="flex items-center gap-2 justify-end pt-2 border-t border-border shrink-0">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSubmit} disabled={submitting || !picked}>
            {submitting ? "⏳ Importing…" : "📥 Import range"}
          </Button>
        </footer>
      </motion.div>
    </AnimatePresence>
  );
}

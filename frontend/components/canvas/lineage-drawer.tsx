"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { api, ApiError } from "@/lib/api/client";
import { PositiveLoader } from "@/components/positive-loader";

interface LineageSource {
  dataset_id: string;
  dataset_label?: string;
  row_index: number;
  row: Record<string, unknown> | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  runId: string;
  rowIndex: number | null;
  outputId?: string;
}

/**
 * Lineage trace drawer.
 *
 * Click a row in a run-output table → this drawer fetches /runs/{id}/lineage
 * and shows the originating source-dataset row(s). Useful for "where did
 * THIS number come from?" debugging.
 *
 * The pipeline must have been run with `metadata.trackLineage = true` in
 * its JSON document, otherwise the backend returns no sources and we show
 * a friendly hint pointing the user at the docs.
 */
export function LineageDrawer({ open, onClose, runId, rowIndex, outputId }: Props) {
  const [loading, setLoading] = useState(false);
  const [sources, setSources] = useState<LineageSource[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || rowIndex === null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSources([]);
    api.getRunLineage(runId, rowIndex, outputId).then(
      (result) => {
        if (cancelled) return;
        setSources(result.sources);
      },
      (e) => {
        if (cancelled) return;
        const msg =
          e instanceof ApiError
            ? typeof e.detail === "object" && e.detail && "detail" in e.detail
              ? String((e.detail as { detail: unknown }).detail)
              : e.message
            : (e as Error).message;
        setError(msg);
      },
    ).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [open, runId, rowIndex, outputId]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="lineage-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/30"
          />
          <motion.aside
            key="lineage-drawer"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 36 }}
            className="fixed top-0 right-0 bottom-0 z-50 w-[480px] bg-card border-l border-border shadow-2xl flex flex-col"
          >
            <header className="px-4 py-3 border-b border-border flex items-center gap-3 shrink-0">
              <span className="text-2xl" aria-hidden>🔍</span>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Lineage · output row {rowIndex}
                </p>
                <p className="font-medium truncate">
                  {loading ? "Tracing…" : sources.length === 0 && !error ? "No upstream sources" : `${sources.length} source row(s)`}
                </p>
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
              {loading && (
                <div className="grid place-items-center py-8">
                  <PositiveLoader
                    variant="rendering"
                    primary="Looking up source rows…"
                    size="sm"
                  />
                </div>
              )}

              {error && (
                <div className="rounded-md border border-rose-300/60 bg-rose-50/40 dark:bg-rose-900/20 p-3 text-sm text-rose-800 dark:text-rose-200">
                  {error}
                </div>
              )}

              {!loading && !error && sources.length === 0 && (
                <div className="rounded-md border border-amber-300/60 bg-amber-50/40 dark:bg-amber-900/20 p-3 text-xs space-y-2">
                  <p className="font-medium">No lineage data for this row.</p>
                  <p className="text-muted-foreground">
                    Lineage tracking is opt-in. Set <code className="font-mono bg-muted px-1 rounded">metadata.trackLineage = true</code>
                    {" "}in the pipeline document and re-run. Then every output row carries a back-reference to its source rows.
                  </p>
                </div>
              )}

              {sources.map((src, i) => (
                <section key={i} className="rounded-md border border-border bg-muted/20 p-3 space-y-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-base" aria-hidden>📦</span>
                    <span className="font-medium">{src.dataset_label || src.dataset_id}</span>
                    <span className="text-muted-foreground">· source row {src.row_index}</span>
                  </div>
                  {src.row ? (
                    <div className="rounded bg-background border border-border/60 overflow-hidden">
                      <table className="text-xs w-full">
                        <tbody>
                          {Object.entries(src.row).map(([col, val]) => (
                            <tr key={col} className="border-b border-border/40 last:border-b-0">
                              <td className="px-2 py-1 text-muted-foreground font-mono whitespace-nowrap align-top w-1/3">
                                {col}
                              </td>
                              <td className="px-2 py-1 font-mono break-all">
                                {val === null || val === undefined
                                  ? <span className="text-muted-foreground/50 italic">null</span>
                                  : typeof val === "object"
                                    ? JSON.stringify(val)
                                    : String(val)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-[11px] text-muted-foreground italic">
                      Source row body wasn't materialised (large dataset?). Only the index is available.
                    </p>
                  )}
                </section>
              ))}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

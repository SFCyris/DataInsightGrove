"use client";

import { motion, AnimatePresence } from "motion/react";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError, type Dataset } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

interface Props {
  /** The just-uploaded dataset in `awaiting_sheet_pick` status. */
  dataset: Dataset;
  onPicked: (next: Dataset) => void;
  onCancel: () => void;
}

/**
 * Modal that surfaces the sheet list of a multi-sheet Excel workbook
 * and lets the user pick which one to ingest.
 *
 * Why this design: the file is already on disk after upload — switching
 * sheets is just re-running ingest with a different `sheet` option. No
 * re-upload needed. We use a real modal (not a side drawer) because the
 * choice is blocking — the dataset isn't usable until the user picks.
 */
export function SheetPickerModal({ dataset, onPicked, onCancel }: Props) {
  const sheets = dataset.availableSheets ?? [];
  const [picked, setPicked] = useState<string>(sheets[0] ?? "");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async () => {
    if (!picked) return;
    setSubmitting(true);
    try {
      const next = await api.pickSheet(dataset.id, picked);
      if (next.status === "failed") {
        toast.error(`Ingest failed: ${next.error ?? "unknown"}`);
      } else {
        toast.success(`📑 Imported "${picked}" sheet (${next.rowCount?.toLocaleString() ?? "?"} rows)`);
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
        key="sheet-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onCancel}
      />
      <motion.div
        key="sheet-modal"
        initial={{ opacity: 0, y: 8, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 360, damping: 28 }}
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[480px] max-w-[92vw] bg-card border border-border rounded-lg shadow-2xl p-5 space-y-4"
        role="dialog"
        aria-label="Pick Excel sheet"
      >
        <header className="flex items-center gap-2">
          <span className="text-2xl" aria-hidden>📑</span>
          <div className="flex-1 min-w-0">
            <h2 className="font-medium truncate">Pick a sheet</h2>
            <p className="text-[11px] text-muted-foreground truncate">
              {dataset.name} · {sheets.length} sheets
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

        <p className="text-xs text-muted-foreground">
          The workbook has multiple sheets. Pick the one to import — the file's
          already on the server, no re-upload.
        </p>

        <div className="max-h-[280px] overflow-y-auto rounded-md border border-border/60 divide-y divide-border/40">
          {sheets.map((s) => (
            <label
              key={s}
              className={[
                "flex items-center gap-2 px-3 py-2 cursor-pointer text-sm",
                picked === s ? "bg-emerald-50 dark:bg-emerald-900/20" : "hover:bg-muted/40",
              ].join(" ")}
            >
              <input
                type="radio"
                name="sheet"
                value={s}
                checked={picked === s}
                onChange={() => setPicked(s)}
              />
              <span className="font-mono">{s}</span>
            </label>
          ))}
        </div>

        <footer className="flex items-center gap-2 justify-end pt-2 border-t border-border">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSubmit} disabled={submitting || !picked}>
            {submitting ? "⏳ Importing…" : "📥 Import sheet"}
          </Button>
        </footer>
      </motion.div>
    </AnimatePresence>
  );
}

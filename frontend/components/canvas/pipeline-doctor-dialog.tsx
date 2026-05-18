"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/button";
import type { Diagnosis } from "@/lib/pipeline-doctor";

/**
 * 🩺 Pipeline tune-up dialog.
 *
 * Surfaces structural diagnoses found by `diagnose()` in a friendly,
 * non-blocking way. Each diagnosis is shown with a short title + the
 * detailed "why" + (when fixable) a preview of the change.
 *
 * UX framing per the loading-state principles:
 *
 *   - **No error language** — header says "tune-up", not "errors". Each
 *     diagnosis's severity surfaces as a tiny pill (info / warn) but
 *     the dialog stays warm-toned (emerald accents, neutral text).
 *   - **Per-issue checkbox** — user can opt out of individual fixes.
 *     Default is "all fixable items checked". Non-fixable items are
 *     informational only with a sub-line explaining what to do.
 *   - **Skip is non-destructive** — picking "Skip for now" leaves the
 *     doc untouched. The runtime fallback paths still work without the
 *     fix. Persisted per-pipeline-and-rule in localStorage so we don't
 *     re-prompt about already-dismissed issues.
 *   - **Apply produces an autosaved checkpoint** — the editor's
 *     standard save path is used, so the user can ⌘Z if they change
 *     their mind. The fix isn't a one-way door.
 */
interface Props {
  open: boolean;
  pipelineId: string;
  diagnoses: Diagnosis[];
  onApply: (selected: Diagnosis[]) => void;
  onSkip: () => void;
}

const SEVERITY_PILL: Record<"info" | "warn", string> = {
  info: "bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300",
  warn: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
};

export function PipelineDoctorDialog({
  open,
  pipelineId,
  diagnoses,
  onApply,
  onSkip,
}: Props) {
  // Default: every fixable diagnosis is checked. The user can untick
  // ones they want to defer. Unfixable diagnoses are display-only.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(diagnoses.filter((d) => d.fixable).map((d) => d.id)),
  );
  const fixableCount = diagnoses.filter((d) => d.fixable).length;
  const selected = diagnoses.filter((d) => d.fixable && selectedIds.has(d.id));

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Round-6 UX#2: modal a11y — focus the primary action on open + ESC
  // dismisses + the dialog's surface gets `aria-modal` (added below).
  // Without these, Tab leaked into the page beneath the backdrop and
  // screen-reader users got no announcement that a dialog opened.
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const primary = dialogRef.current?.querySelector<HTMLButtonElement>(
      "[data-doctor-primary]",
    );
    primary?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onSkip();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onSkip]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="doctor-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onSkip}
            className="fixed inset-0 z-40 bg-black/30"
            aria-hidden="true"
          />
          <motion.div
            key="doctor-dialog"
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 360, damping: 32 }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="pipeline-doctor-title"
            ref={dialogRef}
            className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 w-[600px] max-h-[80vh] overflow-y-auto rounded-xl border border-border bg-card shadow-2xl p-5"
          >
            <header className="flex items-start gap-3 mb-4">
              <span className="text-3xl select-none mt-1" aria-hidden>🩺</span>
              <div className="flex-1">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Pipeline composition
                </p>
                <h2 id="pipeline-doctor-title" className="text-base font-semibold leading-tight">
                  Pipeline tune-up
                </h2>
                <p className="text-[12px] text-muted-foreground mt-1 leading-relaxed">
                  We spotted{" "}
                  {diagnoses.length === 1
                    ? "1 thing"
                    : `${diagnoses.length} things`}{" "}
                  worth tidying up. Reviewing now keeps things consistent across
                  every preview surface — but skipping is fine too, the
                  pipeline still runs.
                </p>
              </div>
              <button
                type="button"
                onClick={onSkip}
                aria-label="Close"
                className="text-muted-foreground hover:text-foreground"
              >
                ✕
              </button>
            </header>

            <ul className="space-y-2.5">
              {diagnoses.map((d) => (
                <li
                  key={d.id}
                  className={[
                    "rounded-lg border px-3 py-2.5",
                    d.fixable
                      ? selectedIds.has(d.id)
                        ? "border-emerald-300/60 bg-emerald-50/50 dark:bg-emerald-900/15 dark:border-emerald-700/50"
                        : "border-border bg-card hover:border-foreground/20"
                      : "border-border bg-muted/30",
                  ].join(" ")}
                >
                  <label className="flex items-start gap-3 cursor-pointer">
                    {d.fixable ? (
                      <input
                        type="checkbox"
                        checked={selectedIds.has(d.id)}
                        onChange={() => toggle(d.id)}
                        className="mt-1 shrink-0"
                      />
                    ) : (
                      <span className="mt-0.5 shrink-0 text-base" aria-hidden>
                        ℹ️
                      </span>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium leading-snug">{d.title}</p>
                        <span
                          className={[
                            "shrink-0 text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded-full",
                            SEVERITY_PILL[d.severity],
                          ].join(" ")}
                        >
                          {d.severity}
                        </span>
                        {!d.fixable && (
                          <span className="text-[10px] text-muted-foreground italic">
                            manual fix
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
                        {d.detail}
                      </p>
                      {d.preview && (
                        <pre className="mt-1.5 text-[10px] font-mono bg-muted/50 rounded px-2 py-1 whitespace-pre-wrap break-all leading-relaxed">
                          {d.preview}
                        </pre>
                      )}
                    </div>
                  </label>
                </li>
              ))}
            </ul>

            <div className="flex justify-end gap-2 mt-5">
              <Button
                size="sm"
                variant="ghost"
                onClick={onSkip}
                title="Don't apply changes. The pipeline still works — runtime fallbacks cover the diagnoses. We won't ask again about these specific issues for this pipeline."
              >
                Skip for now
              </Button>
              <Button
                size="sm"
                disabled={selected.length === 0}
                onClick={() => onApply(selected)}
                data-doctor-primary
              >
                🩺 Apply{" "}
                {selected.length === 0
                  ? ""
                  : selected.length === fixableCount
                    ? `(${fixableCount} fix${fixableCount === 1 ? "" : "es"})`
                    : `(${selected.length}/${fixableCount})`}
              </Button>
            </div>
            <p className="text-[10px] text-muted-foreground/70 mt-2 text-right">
              The result is autosaved. ⌘Z reverts within the editor; or
              💾 Save to lock it in as a labelled checkpoint.
            </p>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

/** Per-pipeline-per-rule dismissal storage. After "Skip for now" we
 *  remember which rule ids the user dismissed so we don't nag them on
 *  subsequent loads of the same pipeline. New rules added later still
 *  surface (the dismiss key includes the rule id). */
const DISMISS_KEY = "dig.pipeline-doctor.dismissed";

export function loadDismissals(): Record<string, string[]> {
  try {
    return JSON.parse(localStorage.getItem(DISMISS_KEY) || "{}");
  } catch {
    return {};
  }
}

export function recordDismissals(pipelineId: string, ruleIds: string[]): void {
  const all = loadDismissals();
  const existing = new Set(all[pipelineId] || []);
  for (const r of ruleIds) existing.add(r);
  all[pipelineId] = Array.from(existing);
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify(all));
  } catch {
    /* quota / private mode — non-fatal */
  }
}

export function filterDismissed(
  pipelineId: string,
  diagnoses: Diagnosis[],
): Diagnosis[] {
  const all = loadDismissals();
  const dismissed = new Set(all[pipelineId] || []);
  return diagnoses.filter((d) => !dismissed.has(d.id));
}

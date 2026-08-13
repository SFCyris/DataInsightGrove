"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/button";
import type { PipelineDocument } from "@/lib/api/client";
import { useEscapeToClose } from "@/components/ui/use-dialog-behavior";

/**
 * 🪆 Publish as reusable step — turns the current pipeline into a
 * composable building block that can be inserted into other pipelines
 * via the step picker. Exposed by setting `metadata.publishedAsStep`
 * on the document; consumers see a synthesized manifest from
 * `/steps` and pin to a specific etag of this pipeline.
 *
 * MVP shape: requires exactly one dataset (the implicit `main` input)
 * and one terminal node (the implicit `out` output). The dialog
 * surfaces label / emoji / description / category — the simplest
 * fields a step needs. Exposed params are configured per-node via the
 * "Expose this param" toggle in the param-form (separate UI).
 */

export interface PublishedAsStepConfig {
  label: string;
  description?: string;
  emoji?: string;
  category?: string;
}

interface Props {
  open: boolean;
  doc: PipelineDocument;
  onClose: () => void;
  onPublish: (cfg: PublishedAsStepConfig) => void;
  onUnpublish: () => void;
}

const CATEGORIES = [
  { id: "clean", label: "Clean", emoji: "🧹" },
  { id: "shape", label: "Shape", emoji: "✂️" },
  { id: "derive", label: "Derive", emoji: "➕" },
  { id: "aggregate", label: "Aggregate", emoji: "📊" },
  { id: "combine", label: "Combine", emoji: "🔗" },
  { id: "analyze", label: "Analyze", emoji: "🔬" },
  { id: "model", label: "Model", emoji: "🧠" },
  { id: "validate", label: "Validate", emoji: "✅" },
  { id: "visualize", label: "Visualize", emoji: "📈" },
  { id: "custom", label: "Custom", emoji: "🪆" },
];

export function PublishAsStepDialog({ open, doc, onClose, onPublish, onUnpublish }: Props) {
  // Escape closes this overlay — it previously had no handler at all,
  // while the shortcuts cheatsheet advertised "Esc — Close any overlay".
  // Arbitrated so only the top-most overlay reacts.
  useEscapeToClose(open, onClose);
  const existing =
    (doc.metadata?.publishedAsStep as PublishedAsStepConfig | undefined) ?? null;
  const [draft, setDraft] = useState<PublishedAsStepConfig>(
    existing ?? {
      label: doc.name,
      description: "",
      emoji: "🪆",
      category: "custom",
    },
  );

  const datasetCount = doc.datasets?.length ?? 0;
  const nodeCount = doc.nodes?.length ?? 0;
  const exposedParamCount = (doc.nodes ?? []).reduce((sum, n) => {
    const ui = (n.ui as { exposedParams?: Record<string, unknown> }) ?? {};
    return sum + Object.keys(ui.exposedParams ?? {}).length;
  }, 0);

  const canPublish = draft.label.trim().length > 0 && datasetCount > 0 && nodeCount > 0;
  const blockReason =
    datasetCount === 0
      ? "Pipeline has no datasets — add at least one before publishing."
      : nodeCount === 0
        ? "Pipeline has no transformation steps yet."
        : datasetCount > 1
          ? "MVP: pipelines with multiple datasets can't be published yet. Reduce to one input dataset, or wait for multi-input support."
          : null;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="pub-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/30"
          />
          <motion.div
            key="pub-dialog"
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 360, damping: 32 }}
            role="dialog"
            aria-label="Publish as reusable step"
            className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 max-w-[92vw] w-[560px] max-h-[80vh] overflow-y-auto rounded-xl border border-border bg-card shadow-2xl p-5"
          >
            <header className="flex items-center gap-3 mb-4">
              <span className="text-2xl select-none" aria-hidden>🪆</span>
              <div className="flex-1">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Pipeline composition
                </p>
                <h2 className="text-base font-semibold leading-tight">
                  {existing ? "Edit reusable step" : "Publish as reusable step"}
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

            <p className="text-[12px] text-muted-foreground mb-4 leading-relaxed">
              Once published, this pipeline appears in every other pipeline&apos;s
              step picker. Consumers pin to the version they install, so your
              future edits won&apos;t change their behaviour until they upgrade.
            </p>

            {blockReason && (
              <div className="mb-4 rounded-md border border-amber-300/60 bg-amber-50/60 dark:bg-amber-900/10 px-3 py-2 text-[12px] text-amber-900 dark:text-amber-200">
                ⚠️ {blockReason}
              </div>
            )}

            <div className="space-y-3">
              <Field label="Step label" hint="Shown in the picker. Keep it short.">
                <input
                  type="text"
                  value={draft.label}
                  onChange={(e) => setDraft({ ...draft, label: e.target.value })}
                  placeholder={doc.name}
                  className="w-full rounded-md border border-input bg-background px-2 py-1 text-sm"
                />
              </Field>

              <Field label="Emoji" hint="Single emoji rendered as the step's icon.">
                <input
                  type="text"
                  value={draft.emoji ?? ""}
                  onChange={(e) => setDraft({ ...draft, emoji: e.target.value })}
                  placeholder="🪆"
                  maxLength={4}
                  className="w-20 rounded-md border border-input bg-background px-2 py-1 text-sm text-center"
                />
              </Field>

              <Field label="Description" hint="One sentence — why a consumer would reach for this.">
                <textarea
                  value={draft.description ?? ""}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  placeholder="What this step does in one sentence."
                  rows={2}
                  className="w-full rounded-md border border-input bg-background px-2 py-1 text-sm leading-snug"
                />
              </Field>

              <Field label="Category" hint="Determines where it lands in the 9-outcome picker.">
                <div className="grid grid-cols-5 gap-1.5">
                  {CATEGORIES.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setDraft({ ...draft, category: c.id })}
                      className={[
                        "rounded-md border px-2 py-1.5 text-[11px] flex flex-col items-center gap-0.5 transition-colors",
                        draft.category === c.id
                          ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20"
                          : "border-border hover:border-foreground/30",
                      ].join(" ")}
                    >
                      <span className="text-base" aria-hidden>{c.emoji}</span>
                      <span>{c.label}</span>
                    </button>
                  ))}
                </div>
              </Field>
            </div>

            <div className="mt-4 rounded-md bg-muted/40 p-3 text-[11px] text-muted-foreground space-y-1">
              <p>
                <strong>Inputs / outputs (MVP)</strong>: implicit — one input
                slot named <code className="font-mono">main</code> wired to
                this pipeline&apos;s dataset, one output named{" "}
                <code className="font-mono">out</code> from the terminal step.
              </p>
              <p>
                <strong>Exposed params</strong>: {exposedParamCount} —
                managed per-node via the&nbsp;
                <span className="italic">&ldquo;Expose this param&rdquo;</span>{" "}
                toggle in the params panel.
              </p>
            </div>

            <div className="flex justify-end gap-2 mt-5">
              {existing && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={onUnpublish}
                  title="Remove the publishedAsStep marker — consumers will see this step disappear from their pickers."
                  className="mr-auto text-rose-600 hover:text-rose-700"
                >
                  Unpublish
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!canPublish || !!blockReason}
                onClick={() => onPublish(draft)}
              >
                {existing ? "💾 Save" : "🪆 Publish"}
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_2fr] gap-3 items-start">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{hint}</p>}
      </div>
      <div>{children}</div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  aiApi,
  type AiReviewFinding,
  type AiReviewOut,
  type AiReviewSeverity,
  type AiReviewCategory,
} from "@/lib/api/client";
import { useExpertise } from "@/lib/settings";
import { Button } from "@/components/ui/button";

const SEV_TINT: Record<AiReviewSeverity, string> = {
  high: "border-rose-500/60 bg-rose-50/60 dark:bg-rose-900/20",
  warn: "border-amber-500/60 bg-amber-50/60 dark:bg-amber-900/20",
  info: "border-sky-500/60 bg-sky-50/60 dark:bg-sky-900/20",
};

const SEV_BADGE: Record<AiReviewSeverity, string> = {
  high: "🔴 HIGH",
  warn: "🟡 WARN",
  info: "🔵 INFO",
};

const CAT_EMOJI: Record<AiReviewCategory, string> = {
  performance: "⚡",
  correctness: "🎯",
  quality: "✅",
  lineage: "🔗",
  ergonomics: "✨",
};

const DISMISSED_KEY = (pid: string) => `dig.review.dismissed.${pid}`;

function findingHash(f: AiReviewFinding): string {
  return `${f.category}:${f.title}:${f.affected_nodes.join(",")}`;
}

function readDismissed(pipelineId: string): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(DISMISSED_KEY(pipelineId));
    if (!raw) return new Set();
    return new Set(JSON.parse(raw));
  } catch {
    return new Set();
  }
}

function writeDismissed(pipelineId: string, set: Set<string>) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(DISMISSED_KEY(pipelineId), JSON.stringify([...set]));
  } catch {
    /* ignore */
  }
}

interface Props {
  pipelineId: string;
  /** Called when user clicks an "affected node" to focus it in the editor. */
  onFocusNode?: (nodeId: string) => void;
}

/**
 * AI Pipeline Reviewer panel.
 *
 * Trigger button on the editor toolbar (gated to Builder+ via useExpertise).
 * Drawer-style overlay with severity-ranked finding cards.
 */
export function ReviewPanel({ pipelineId, onFocusNode }: Props) {
  const { isAtLeast } = useExpertise();
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<AiReviewOut | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(() => readDismissed(pipelineId));
  const [showDismissed, setShowDismissed] = useState(false);

  // Load dismissed for this pipeline whenever id changes.
  useEffect(() => {
    setDismissed(readDismissed(pipelineId));
  }, [pipelineId]);

  // Esc to close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const reviewMutation = useMutation({
    mutationFn: () => aiApi.reviewPipeline(pipelineId),
    onSuccess: (out) => {
      setData(out);
      if (out.findings.length === 0) {
        toast.success("✨ No findings — pipeline looks clean.");
      } else {
        const high = out.findings.filter((f) => f.severity === "high").length;
        toast.success(
          `${out.findings.length} finding${out.findings.length === 1 ? "" : "s"}` +
            (high ? ` — ${high} high-severity` : ""),
        );
      }
    },
    onError: (e: Error) => toast.error(`Review failed: ${e.message}`),
  });

  if (!isAtLeast("builder")) return null;

  const dismissFinding = (f: AiReviewFinding) => {
    const next = new Set(dismissed);
    next.add(findingHash(f));
    setDismissed(next);
    writeDismissed(pipelineId, next);
  };

  const undismiss = (hash: string) => {
    const next = new Set(dismissed);
    next.delete(hash);
    setDismissed(next);
    writeDismissed(pipelineId, next);
  };

  const visibleFindings = (data?.findings ?? []).filter(
    (f) => !dismissed.has(findingHash(f)),
  );
  const hiddenFindings = (data?.findings ?? []).filter((f) =>
    dismissed.has(findingHash(f)),
  );

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          setOpen(true);
          if (!data) reviewMutation.mutate();
        }}
        title="AI Pipeline Review — find performance, correctness, and quality issues"
        aria-label="Review pipeline with AI"
      >
        🔍 Review
      </Button>

      {/* Portal to <body> so the fixed drawer escapes the editor header's
          stacking context (the header is `position: relative` and would
          otherwise clip the drawer to its own height). */}
      {typeof document !== "undefined" && createPortal(
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm"
              onClick={() => setOpen(false)}
            />
            <motion.aside
              initial={reduce ? { opacity: 0 } : { x: "100%" }}
              animate={reduce ? { opacity: 1 } : { x: 0 }}
              exit={reduce ? { opacity: 0 } : { x: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="fixed right-0 top-0 bottom-0 z-50 w-[min(720px,100vw)] bg-background border-l border-border shadow-2xl flex flex-col"
              role="dialog"
              aria-label="AI Pipeline Review"
            >
              <header className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/40">
                <span className="text-xl select-none" aria-hidden>🔍</span>
                <div className="flex-1 min-w-0">
                  <h2 className="text-sm font-semibold tracking-tight">Pipeline review</h2>
                  {data && (
                    <p className="text-[10px] text-muted-foreground tabular-nums">
                      {data.model} ·{" "}
                      {visibleFindings.length} active finding
                      {visibleFindings.length === 1 ? "" : "s"}
                      {hiddenFindings.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setShowDismissed((v) => !v)}
                          className="ml-2 underline underline-offset-2"
                        >
                          {showDismissed ? "hide" : "show"} {hiddenFindings.length} dismissed
                        </button>
                      )}
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => reviewMutation.mutate()}
                  disabled={reviewMutation.isPending}
                  title="Run review again"
                >
                  {reviewMutation.isPending ? "⏳" : "🔄"}
                </Button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="text-xs text-muted-foreground hover:text-foreground rounded px-2 py-1 hover:bg-muted"
                >
                  ✕
                </button>
              </header>

              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {reviewMutation.isPending && (
                  <p className="text-sm text-muted-foreground">⏳ Reviewing pipeline…</p>
                )}
                {data && data.rawText && (
                  <div className="rounded-lg border border-border bg-muted/40 p-3 text-xs">
                    <p className="font-medium mb-1">⚠ Couldn't parse model output</p>
                    <pre className="text-[10px] text-muted-foreground overflow-auto">
                      {data.rawText.slice(0, 800)}
                    </pre>
                  </div>
                )}
                {data && visibleFindings.length === 0 && !reviewMutation.isPending && (
                  <div className="text-center py-12">
                    <span className="text-5xl select-none" aria-hidden>✨</span>
                    <p className="mt-3 text-sm text-muted-foreground">
                      No findings — pipeline looks clean.
                    </p>
                  </div>
                )}
                {visibleFindings.map((f, i) => (
                  <FindingCard
                    key={`${i}-${findingHash(f)}`}
                    f={f}
                    onDismiss={() => dismissFinding(f)}
                    onFocusNode={onFocusNode}
                  />
                ))}
                {showDismissed && hiddenFindings.length > 0 && (
                  <section>
                    <h3 className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 mt-4">
                      Dismissed
                    </h3>
                    {hiddenFindings.map((f, i) => (
                      <div
                        key={`d-${i}`}
                        className="rounded-md border border-border bg-card/30 px-2 py-1.5 text-xs flex items-center gap-2 mb-1.5 opacity-70"
                      >
                        <span aria-hidden>{CAT_EMOJI[f.category]}</span>
                        <span className="flex-1 truncate">{f.title}</span>
                        <button
                          type="button"
                          onClick={() => undismiss(findingHash(f))}
                          className="text-[10px] underline underline-offset-2 hover:text-foreground"
                        >
                          restore
                        </button>
                      </div>
                    ))}
                  </section>
                )}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>,
      document.body)}
    </>
  );
}

function FindingCard({
  f,
  onDismiss,
  onFocusNode,
}: {
  f: AiReviewFinding;
  onDismiss: () => void;
  onFocusNode?: (nodeId: string) => void;
}) {
  const { isAtLeast } = useExpertise();
  return (
    <article
      className={["rounded-lg border p-3 text-sm space-y-2", SEV_TINT[f.severity]].join(" ")}
    >
      <header className="flex items-start gap-2">
        <span
          className="text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-full bg-background/60 border border-border"
        >
          {SEV_BADGE[f.severity]}
        </span>
        <h3 className="font-medium leading-tight flex-1">
          <span className="mr-1.5" aria-hidden>{CAT_EMOJI[f.category]}</span>
          {f.title}
        </h3>
        {isAtLeast("engineer") && (
          <span
            className="text-[10px] text-muted-foreground tabular-nums"
            title={`Confidence: ${(f.confidence * 100).toFixed(0)}%`}
          >
            {(f.confidence * 100).toFixed(0)}%
          </span>
        )}
      </header>
      <p className="text-xs text-muted-foreground leading-relaxed">{f.explanation}</p>
      {f.affected_nodes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {f.affected_nodes.map((nid) => (
            <button
              key={nid}
              type="button"
              onClick={() => onFocusNode?.(nid)}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-border bg-background/60 hover:bg-background"
            >
              #{nid.slice(-8)}
            </button>
          ))}
        </div>
      )}
      <footer className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={onDismiss}
          className="text-[10px] text-muted-foreground hover:text-foreground underline underline-offset-2"
        >
          Dismiss
        </button>
      </footer>
    </article>
  );
}

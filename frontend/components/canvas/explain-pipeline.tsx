"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { aiApi, ApiError } from "@/lib/api/client";

/**
 * Toolbar button that asks the configured AI to explain the current
 * pipeline. Opens a side drawer with the rendered Markdown narrative
 * and a copy-to-clipboard button.
 *
 * Gracefully degrades when AI is disabled — the 400 from the backend
 * surfaces as a toast pointing the user at Settings → AI.
 */
export function ExplainPipelineButton({ pipelineId }: { pipelineId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Gate the portal on a client-only mount flag so we don't call
  // createPortal during SSR (document doesn't exist there).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const onClick = async () => {
    setOpen(true);
    setLoading(true);
    setText(null);
    setError(null);
    setModel(null);
    try {
      const out = await aiApi.explainPipeline(pipelineId);
      setText(out.markdown);
      setModel(out.model);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    if (!text) return;
    navigator.clipboard.writeText(text).then(
      () => toast.success("Copied"),
      () => toast.error("Copy failed"),
    );
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={onClick}
        title="Generate a plain-English description of this pipeline"
      >
        ✨ Explain
      </Button>

      {/* Portaled to document.body so `position: fixed` resolves against the
          viewport, not the toolbar. The toolbar uses `backdrop-blur` which
          creates a containing block for fixed descendants — without the
          portal, this drawer would shrink to the toolbar's bounds.
          AnimatePresence MUST live inside the portal: when wrapped around
          createPortal it sees the portal as one opaque child and never
          mounts the inner motion components. */}
      {mounted && createPortal(
        <AnimatePresence>
          {open && (
          <>
            <motion.div
              key="explain-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-40 bg-black/30"
            />
            <motion.aside
              key="explain-drawer"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 36 }}
              className="fixed top-0 right-0 bottom-0 z-50 w-[460px] bg-card border-l border-border shadow-2xl flex flex-col"
            >
              <header className="px-4 py-3 border-b border-border flex items-center gap-3 shrink-0">
                <span className="text-2xl" aria-hidden>✨</span>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">AI explanation</p>
                  <p className="font-medium truncate">
                    {loading ? "Thinking…" : model ? `via ${model}` : "Pipeline narrative"}
                  </p>
                </div>
                {text && (
                  <Button size="sm" variant="ghost" onClick={copy} title="Copy to clipboard">
                    📋
                  </Button>
                )}
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close"
                  className="text-muted-foreground hover:text-foreground"
                >
                  ✕
                </button>
              </header>

              <div className="overflow-y-auto flex-1 p-5">
                {loading && (
                  <div className="text-sm text-muted-foreground space-y-2">
                    <p>⏳ Building the prompt and waiting on the model…</p>
                    <p className="text-[11px]">First call to a cold local model can take 30–60s.</p>
                  </div>
                )}
                {error && (
                  <div className="rounded-md border border-rose-300/50 bg-rose-50/40 dark:bg-rose-900/10 p-3 text-sm text-rose-800 dark:text-rose-200 space-y-2">
                    <p className="font-medium">AI request failed</p>
                    <p className="text-xs whitespace-pre-wrap break-words">{error}</p>
                    <p className="text-xs opacity-80">
                      Check <a className="underline" href="/settings#ai">Settings → AI</a> and use Test connection.
                    </p>
                  </div>
                )}
                {text && (
                  // Plain-text rendering of the model's Markdown. We deliberately
                  // do NOT use a Markdown renderer here — keeps the dependency
                  // surface tight and avoids an injection risk if the model
                  // emits unexpected HTML. The model is instructed to output
                  // simple paragraphs anyway.
                  <article className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap text-sm leading-relaxed">
                    {text}
                  </article>
                )}
              </div>
            </motion.aside>
          </>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}

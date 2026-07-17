"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { aiApi, ApiError, API_BASE, API_TOKEN } from "@/lib/api/client";
import { PositiveLoader } from "@/components/positive-loader";

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
  const reduce = useReducedMotion();
  // Monotonic request id — a re-click mid-stream abandons the previous
  // stream's state updates instead of interleaving two generations.
  const reqRef = useRef(0);
  // Controller for the in-flight SSE fetch — aborting it drops the
  // connection, which the backend detects and cancels generation.
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    // Abort any in-flight stream on unmount — invalidate the request id
    // first so the aborted fetch doesn't kick off the fallback path.
    return () => {
      reqRef.current++;
      abortRef.current?.abort();
    };
  }, []);

  const close = () => {
    // Invalidate the active request first so the abort's rejection
    // doesn't trigger the non-streaming fallback, then drop the stream.
    reqRef.current++;
    abortRef.current?.abort();
    setOpen(false);
  };

  /**
   * Consume the SSE stream from /ai/explain-pipeline/{id}/stream,
   * appending deltas into `text` as they arrive so the narrative renders
   * progressively. Throws if the stream fails before the first delta —
   * the caller then falls back to the one-shot endpoint.
   */
  const streamExplanation = async (req: number, signal: AbortSignal) => {
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    if (API_TOKEN) headers["Authorization"] = `Bearer ${API_TOKEN}`;
    const res = await fetch(
      `${API_BASE}/ai/explain-pipeline/${pipelineId}/stream`,
      { method: "POST", headers, signal },
    );
    if (!res.ok || !res.body) throw new Error(`stream unavailable (${res.status})`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let received = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (req !== reqRef.current) {
        // A newer request took over — stop pulling and drop the stream.
        reader.cancel().catch(() => {});
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      // SSE events are blank-line separated; each event here is a
      // single `data: ...` line.
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const event of events) {
        const line = event.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const data = line.slice("data:".length).trim();
        if (data === "[DONE]") continue;
        let payload: { model?: string; delta?: string; error?: string };
        try {
          payload = JSON.parse(data);
        } catch {
          continue;
        }
        if (payload.model) setModel(payload.model);
        if (payload.error) {
          // Provider failed mid-generation. Nothing received yet →
          // throw so the caller retries non-streaming; otherwise keep
          // the partial text and surface the error alongside it.
          if (!received) throw new Error(payload.error);
          setError(payload.error);
          return;
        }
        if (payload.delta) {
          received += payload.delta;
          setLoading(false); // first token — swap the loader for live text
          setText(received);
        }
      }
    }
    if (!received) throw new Error("stream produced no text");
  };

  const onClick = async () => {
    const req = ++reqRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setOpen(true);
    setLoading(true);
    setText(null);
    setError(null);
    setModel(null);
    try {
      await streamExplanation(req, controller.signal);
    } catch {
      // Streaming failed before any text arrived (backend without the
      // stream route, buffering proxy, provider error) — fall back to
      // the one-shot endpoint.
      if (req !== reqRef.current) return;
      try {
        const out = await aiApi.explainPipeline(pipelineId);
        if (req !== reqRef.current) return;
        setText(out.markdown);
        setModel(out.model);
      } catch (e) {
        if (req !== reqRef.current) return;
        const msg =
          e instanceof ApiError
            ? typeof e.detail === "object" && e.detail && "detail" in e.detail
              ? String((e.detail as { detail: unknown }).detail)
              : e.message
            : (e as Error).message;
        setError(msg);
      }
    } finally {
      if (req === reqRef.current) setLoading(false);
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
              onClick={close}
              className="fixed inset-0 z-40 bg-black/30"
            />
            <motion.aside
              key="explain-drawer"
              initial={reduce ? { opacity: 0 } : { x: "100%" }}
              animate={reduce ? { opacity: 1 } : { x: 0 }}
              exit={reduce ? { opacity: 0 } : { x: "100%" }}
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
                  onClick={close}
                  aria-label="Close"
                  className="text-muted-foreground hover:text-foreground"
                >
                  ✕
                </button>
              </header>

              <div className="overflow-y-auto flex-1 p-5">
                {loading && (
                  <div className="grid place-items-center py-12">
                    <PositiveLoader
                      variant="thinking"
                      primary="Asking the model…"
                    />
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

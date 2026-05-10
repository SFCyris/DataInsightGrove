"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { aiApi, ApiError, type AiSuggestion } from "@/lib/api/client";
import { ThinkingLabel } from "@/components/positive-loader";

interface Props {
  pipelineId: string;
  focusedNodeId: string | null;
  focusedSchema: Record<string, string>;
  /** Called with a suggestion the user clicked Apply on. The pipeline editor
   *  decides where to insert the step (typically appended after the focused
   *  node, with the same input wiring). */
  onApply: (suggestion: AiSuggestion) => void;
}

/**
 * "✨ Suggest" — opens a small modal where the user types a goal in plain
 * English, AI returns 1–3 candidate next steps. Each suggestion shows the
 * step label + the rationale + a confidence chip; click Apply to drop it
 * into the pipeline.
 */
export function SuggestNextButton({ pipelineId, focusedNodeId, focusedSchema, onApply }: Props) {
  const [open, setOpen] = useState(false);
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<AiSuggestion[]>([]);
  const [model, setModel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Gate the portal on a client-only mount flag — see explain-pipeline for
  // the full rationale (createPortal can't run during SSR).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const ask = async () => {
    if (!goal.trim()) return;
    setLoading(true);
    setSuggestions([]);
    setError(null);
    try {
      const out = await aiApi.suggestNextStep({
        pipeline_id: pipelineId,
        focused_node_id: focusedNodeId,
        focused_schema: focusedSchema,
        goal: goal.trim(),
      });
      setSuggestions(out.suggestions);
      setModel(out.model);
      if (out.suggestions.length === 0) {
        setError("AI couldn't find a matching step. Try rephrasing or adding more context.");
      }
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

  const apply = (s: AiSuggestion) => {
    onApply(s);
    toast.success(`Added ${s.step_id}`);
    setOpen(false);
    setSuggestions([]);
    setGoal("");
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setOpen(true)}
        title="Describe what to do next; AI suggests step(s) to drop into the pipeline"
      >
        ✨ Suggest
      </Button>

      {/* Portaled to document.body so `position: fixed` resolves against the
          viewport, not the toolbar. The toolbar uses `backdrop-blur` which
          creates a containing block for fixed descendants — without the
          portal, this modal would be centered inside the toolbar (so half
          off-screen above the page).
          AnimatePresence MUST live inside the portal: when wrapped around
          createPortal it sees the portal as one opaque child and never
          mounts the inner motion components. */}
      {mounted && createPortal(
        <AnimatePresence>
          {open && (
          <>
            <motion.div
              key="suggest-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-40 bg-black/30"
            />
            <motion.div
              key="suggest-modal"
              initial={{ opacity: 0, y: 8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ type: "spring", stiffness: 360, damping: 28 }}
              // max-h + flex-col so content scrolls inside the dialog instead
              // of pushing the header / footer off-screen when 3 suggestions
              // come back. Same pattern as IslandPickerModal.
              className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[600px] max-w-[92vw] max-h-[88vh] bg-card border border-border rounded-lg shadow-2xl p-5 flex flex-col gap-4"
              role="dialog"
              aria-label="Suggest next step with AI"
            >
              <header className="flex items-center gap-2 shrink-0">
                <span className="text-xl" aria-hidden>✨</span>
                <h2 className="font-medium">Suggest next step</h2>
                <span className="flex-1" />
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Close"
                >
                  ✕
                </button>
              </header>

              <div className="flex-1 overflow-y-auto min-h-0 space-y-4 -mx-1 px-1">
                <div>
                  <label className="text-[10px] uppercase tracking-widest text-muted-foreground block mb-1">
                    What do you want to do next?
                  </label>
                  <textarea
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    placeholder="e.g. keep only US customers, or compute revenue per plan tier, or extract email from the JSON column"
                    className="w-full text-sm rounded-md border border-input bg-background px-3 py-2 min-h-[80px]"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
                    }}
                  />
                  <p className="text-[10px] text-muted-foreground mt-1">
                    ⌘+Enter to submit. AI sees the {Object.keys(focusedSchema).length}-column schema at the focused node.
                  </p>
                </div>

                {suggestions.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                      Suggestions {model && <span className="ml-1">via {model}</span>}
                    </p>
                    {suggestions.map((s, i) => (
                      <div
                        key={i}
                        className="rounded-md border border-border bg-muted/20 p-3 space-y-2"
                      >
                        <div className="flex items-start gap-2">
                          <code className="text-xs font-mono px-2 py-0.5 rounded bg-background border border-border">
                            {s.step_id}
                          </code>
                          <span className={[
                            "text-[9px] px-1.5 py-0.5 rounded-full ml-auto shrink-0",
                            s.confidence === "high" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300" :
                            s.confidence === "medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" :
                            "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
                          ].join(" ")}>
                            {s.confidence}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">{s.why}</p>
                        {Object.keys(s.params).length > 0 && (
                          <pre className="text-[10px] font-mono p-2 rounded bg-background/60 overflow-x-auto">
                            {JSON.stringify(s.params, null, 2)}
                          </pre>
                        )}
                        <div className="flex justify-end">
                          <Button size="sm" onClick={() => apply(s)}>✓ Apply</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {error && (
                  <p className="text-xs text-rose-600 dark:text-rose-400 break-words">
                    {error}
                  </p>
                )}
              </div>

              <footer className="flex items-center gap-2 justify-end pt-2 border-t border-border shrink-0">
                <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                  Close
                </Button>
                <Button
                  size="sm"
                  onClick={ask}
                  disabled={loading || !goal.trim()}
                >
                  {loading ? <ThinkingLabel text="Asking…" /> : suggestions.length > 0 ? "Try again" : "✨ Suggest"}
                </Button>
              </footer>
            </motion.div>
          </>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}

"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { aiApi, ApiError, type AiFixExpressionOut } from "@/lib/api/client";
import { ThinkingLabel } from "@/components/positive-loader";

interface Props {
  /** Current value of the expression field. */
  expression: string;
  /** Schema columns visible to this expression — usually upstream `in` port. */
  columns: Array<{ name: string; type: string }>;
  /** "predicate" for filter_rows; "scalar" for derive_column. */
  kind: "predicate" | "scalar";
  /** Optional latest validation error message — gives the AI more to work with. */
  error?: string;
  /** Called with the suggested expression when the user clicks Apply. */
  onApply: (next: string) => void;
}

/**
 * Compact "✨ Fix" button next to expression fields. Opens a popover
 * where the user can optionally describe their intent in plain English,
 * then asks the AI for a corrected expression. Shows the current vs
 * suggested side by side; user clicks Apply or Discard.
 *
 * Gracefully degrades when AI is disabled — the 400 from the backend
 * surfaces as a toast pointing the user at Settings → AI.
 */
export function FixExpressionButton({ expression, columns, kind, error, onApply }: Props) {
  const [open, setOpen] = useState(false);
  const [intent, setIntent] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiFixExpressionOut | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  // Gate the portal on a client-only mount flag — see explain-pipeline for
  // the full rationale (createPortal can't run during SSR).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const ask = async () => {
    setLoading(true);
    setResult(null);
    setErrMsg(null);
    try {
      const r = await aiApi.fixExpression({
        expression,
        columns,
        intent: intent.trim() || undefined,
        error,
        kind,
      });
      setResult(r);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      setErrMsg(msg);
    } finally {
      setLoading(false);
    }
  };

  const apply = () => {
    if (!result) return;
    onApply(result.fixed);
    toast.success("Applied AI suggestion");
    setOpen(false);
    setResult(null);
    setIntent("");
  };

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        className="text-[11px] h-6 px-2"
        onClick={() => setOpen(true)}
        title="Ask AI to suggest a fix or improvement for this expression"
      >
        ✨ Fix
      </Button>

      {/* Portaled to document.body so `position: fixed` resolves against the
          viewport, not whatever ancestor (like a `backdrop-blur` toolbar)
          might own a containing block for fixed descendants.
          AnimatePresence MUST live inside the portal: when wrapped around
          createPortal it sees the portal as one opaque child and never
          mounts the inner motion components. */}
      {mounted && createPortal(
        <AnimatePresence>
          {open && (
          <>
            <motion.div
              key="fix-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-40 bg-black/30"
            />
            <motion.div
              key="fix-modal"
              initial={{ opacity: 0, y: 8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ type: "spring", stiffness: 360, damping: 28 }}
              // max-h + flex-col so a long expression / explanation
              // doesn't push the header / footer off-screen.
              className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[560px] max-w-[92vw] max-h-[88vh] bg-card border border-border rounded-lg shadow-2xl p-5 flex flex-col gap-4"
              role="dialog"
              aria-label="Fix expression with AI"
            >
              <header className="flex items-center gap-2 shrink-0">
                <span className="text-xl" aria-hidden>✨</span>
                <h2 className="font-medium">Fix expression with AI</h2>
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
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Current</p>
                <pre className="text-xs font-mono p-2 rounded bg-muted/40 whitespace-pre-wrap break-all">
                  {expression || <span className="text-muted-foreground">(empty)</span>}
                </pre>
                {error && (
                  <p className="text-[11px] text-rose-600 dark:text-rose-400 mt-1">DuckDB: {error}</p>
                )}
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 block">
                  Describe your intent (optional)
                </label>
                <textarea
                  value={intent}
                  onChange={(e) => setIntent(e.target.value)}
                  placeholder={kind === "predicate"
                    ? "e.g. keep only customers in the US, GB, or JP"
                    : "e.g. amount in EUR, converting at 1.07"}
                  className="w-full text-sm rounded-md border border-input bg-background px-2 py-1.5 min-h-[60px]"
                />
                <p className="text-[10px] text-muted-foreground mt-1">
                  AI sees the columns ({columns.length} available) + the current expression. A few words
                  of intent helps a lot.
                </p>
              </div>

              {result && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1 flex items-center gap-2">
                    Suggested
                    <span className={[
                      "text-[9px] px-1.5 py-0.5 rounded-full",
                      result.confidence === "high" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300" :
                      result.confidence === "medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" :
                      "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
                    ].join(" ")}>
                      {result.confidence} confidence
                    </span>
                  </p>
                  <pre className="text-xs font-mono p-2 rounded bg-emerald-50/60 dark:bg-emerald-900/20 whitespace-pre-wrap break-all">
                    {result.fixed}
                  </pre>
                  {result.explanation && (
                    <p className="text-[11px] text-muted-foreground mt-1">{result.explanation}</p>
                  )}
                </div>
              )}

              {errMsg && (
                <p className="text-xs text-rose-600 dark:text-rose-400 break-words">
                  {errMsg}
                </p>
              )}
              </div>

              <footer className="flex items-center gap-2 justify-end pt-2 border-t border-border shrink-0">
                <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                {result ? (
                  <>
                    <Button variant="outline" size="sm" onClick={ask} disabled={loading}>
                      {loading ? <ThinkingLabel text="Asking…" /> : "Try again"}
                    </Button>
                    <Button size="sm" onClick={apply}>
                      ✓ Apply
                    </Button>
                  </>
                ) : (
                  <Button size="sm" onClick={ask} disabled={loading}>
                    {loading ? <ThinkingLabel text="Asking…" /> : "✨ Suggest fix"}
                  </Button>
                )}
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

"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { aiApi, ApiError, type AiSuggestion, type StepManifest } from "@/lib/api/client";
import { PositiveLoaderInline } from "@/components/positive-loader";

// ─────────────────────────────────────────────────────────────────
// AI ribbon — first row of the QuickAddMenu when AI is configured
// and there's enough context (pipeline + focused node) to make a
// useful suggestion.
//
// Why opt-in (button) and not auto-fetch:
//
//   - Calling the LLM costs the user money/quota every picker open.
//   - Picker open is on the hot path; we want it instant.
//   - The user already knows they want to add a step; auto-suggesting
//     before they've expressed any intent yields a 50/50 hit rate at
//     best.
//
// Click-to-fetch: a single, prominent CTA at the top of the picker.
// On click, replaces itself with the suggestion cards. ~1-3s LLM
// latency, signalled with a spinner. Cached in-component for the
// session — clicking again re-asks (the user wanted a different cut).
// ─────────────────────────────────────────────────────────────────

interface Props {
  pipelineId: string;
  focusedNodeId: string;
  focusedSchema: Record<string, string>;
  steps: StepManifest[];
  onApply: (step: StepManifest, params: Record<string, unknown>) => void;
}

/** Ask the LLM passively — no user-typed goal, just "what makes sense
 *  given what's here?" — by sending a generic, schema-aware prompt.
 *  The system prompt requires a goal; this fills the slot with one
 *  that lets the model answer descriptively rather than refuse. */
const PASSIVE_GOAL =
  "Suggest the most useful next 1-3 steps given the data shape. " +
  "Prefer foundational moves: clean obvious issues, summarise the " +
  "interesting columns, or set up a comparison the user might want.";

export function AiRibbon({ pipelineId, focusedNodeId, focusedSchema, steps, onApply }: Props) {
  // Hide the entire ribbon when AI is disabled — same probe used by
  // suggest-fix.tsx, so reuse the cache key for free.
  const cfgQ = useQuery({
    queryKey: ["ai", "config"],
    queryFn: aiApi.config,
    staleTime: 60_000,
  });

  const [suggestions, setSuggestions] = useState<AiSuggestion[] | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Keyed by step id for O(1) lookup when rendering a suggestion card —
  // we want the human label + emoji, not the bare step_id.
  const stepsById = useMemo(() => {
    const out: Record<string, StepManifest> = {};
    for (const s of steps) out[s.id] = s;
    return out;
  }, [steps]);

  if (!cfgQ.data?.enabled) return null;

  const ask = async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await aiApi.suggestNextStep({
        pipeline_id: pipelineId,
        focused_node_id: focusedNodeId,
        focused_schema: focusedSchema,
        goal: PASSIVE_GOAL,
      });
      setSuggestions(out.suggestions);
      setModel(out.model);
      if (out.suggestions.length === 0) {
        setError("No suggestions — the upstream node may already be at a natural stopping point.");
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

  return (
    <div className="mb-2 border-b border-border/40 pb-2">
      <div className="flex items-center justify-between px-2 py-1">
        <p className="text-[10px] uppercase tracking-wider text-violet-700 dark:text-violet-300">
          ✨ AI suggestions
        </p>
        {suggestions !== null && (
          <button
            type="button"
            onClick={ask}
            disabled={loading}
            className="text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
            title="Ask again with a fresh prompt"
          >
            {loading ? "…" : "↻"}
          </button>
        )}
      </div>
      {/* Initial state: a single CTA button. Compact (one-line) so it
          doesn't push the catalog down too far. */}
      {suggestions === null && !loading && (
        <button
          type="button"
          onClick={ask}
          className="w-full text-left px-2 py-1.5 rounded-md text-sm bg-gradient-to-r from-violet-50 to-fuchsia-50 dark:from-violet-950/40 dark:to-fuchsia-950/40 border border-violet-200/60 dark:border-violet-800/60 hover:from-violet-100 hover:to-fuchsia-100 dark:hover:from-violet-900/50 dark:hover:to-fuchsia-900/50 transition-colors flex items-center gap-2"
        >
          <span aria-hidden>✨</span>
          <span className="flex-1">Ask AI: what should I add next?</span>
          <span className="text-[10px] text-muted-foreground">~2s</span>
        </button>
      )}
      {loading && (
        <div className="px-2 py-3">
          <PositiveLoaderInline
            variant="thinking"
            size="sm"
            text="Thinking about your pipeline…"
          />
        </div>
      )}
      <AnimatePresence>
        {suggestions !== null && suggestions.length > 0 && (
          <motion.ul
            key="ai-list"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-1"
          >
            {suggestions.map((s, i) => {
              const m = stepsById[s.step_id];
              if (!m) return null;
              return (
                <motion.li
                  key={`${s.step_id}-${i}`}
                  initial={{ opacity: 0, y: -2 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.04 * i }}
                >
                  <button
                    type="button"
                    onClick={() => onApply(m, s.params ?? {})}
                    title={s.why || m.description}
                    className="w-full text-left px-2 py-1.5 rounded-md text-sm bg-gradient-to-r from-violet-50/60 to-transparent dark:from-violet-950/20 dark:to-transparent hover:from-violet-100 dark:hover:from-violet-900/40 transition-colors flex flex-col"
                  >
                    <span className="flex items-center gap-1.5">
                      <span>{m.label}</span>
                      <span
                        className={[
                          "ml-auto text-[9px] px-1.5 py-0.5 rounded-full shrink-0",
                          s.confidence === "high"
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                            : s.confidence === "medium"
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                              : "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
                        ].join(" ")}
                      >
                        {s.confidence}
                      </span>
                    </span>
                    {s.why && (
                      <span className="text-[10px] text-muted-foreground line-clamp-2">
                        {s.why}
                      </span>
                    )}
                  </button>
                </motion.li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
      {error && (
        <p className="px-2 py-1.5 text-[11px] text-rose-600 dark:text-rose-400">
          {error}
        </p>
      )}
      {model && suggestions !== null && suggestions.length > 0 && (
        <p className="px-2 pt-1 text-[9px] text-muted-foreground/80">
          via {model}
        </p>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { aiApi, ApiError, type AiVizSuggestion, type StepManifest } from "@/lib/api/client";
import { PositiveLoaderInline } from "@/components/positive-loader";

// ─────────────────────────────────────────────────────────────────
// AI Viz Hints — domain-aware chart suggestions for the focused
// dataset. Hidden when AI is disabled. Click-to-fetch (not auto)
// because it's an LLM call: keeps the Hints panel instant on first
// open, costs the user nothing until they ask. Subsequent fetches
// re-prompt with a fresh seed (the model temperature is 0.2 so
// outputs are mostly stable).
//
// Each card maps to a viz step in the catalog. "Apply" hands the
// step + AI-supplied params up to the parent, which inserts a node
// after the current focus — same path as the column-menu's
// `visualize_as` action, so the integration cost is zero.
// ─────────────────────────────────────────────────────────────────

interface Props {
  /** Pipeline whose document supplies the project name + sampling config. */
  pipelineId: string;
  /** Id of the focused node — dataset alias OR step output id.
   *  Viz suggestions are tailored to that node's actual output
   *  (sampled per the pipeline's chosen method). */
  nodeId: string;
  /** Optional human-readable label for the focused node. */
  nodeLabel?: string;
  steps: StepManifest[];
  onApply: (step: StepManifest, params: Record<string, unknown>) => void;
}

const CONF_PILL: Record<AiVizSuggestion["confidence"], string> = {
  high: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  low: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

export function AiVizHints({ nodeId, pipelineId, nodeLabel, steps, onApply }: Props) {
  // Reuse the global AI config cache key so toggling AI in Settings
  // invalidates here in lockstep.
  const cfgQ = useQuery({
    queryKey: ["ai", "config"],
    queryFn: aiApi.config,
    staleTime: 60_000,
  });

  const [shouldFetch, setShouldFetch] = useState(false);

  const suggestQ = useQuery({
    queryKey: ["ai", "viz-suggestions", pipelineId, nodeId],
    queryFn: () =>
      aiApi.suggestVisualizations({ pipeline_id: pipelineId, node_id: nodeId }),
    enabled: shouldFetch && !!cfgQ.data?.enabled,
    staleTime: 60 * 60_000, // an hour — the schema doesn't change unless the dataset does
    retry: false,
  });

  if (!cfgQ.data?.enabled) return null;

  const stepById: Record<string, StepManifest> = {};
  for (const s of steps) stepById[s.id] = s;

  return (
    <div className="mb-3 rounded-lg border border-violet-200/60 dark:border-violet-800/50 bg-gradient-to-br from-violet-50/60 to-fuchsia-50/30 dark:from-violet-950/30 dark:to-fuchsia-950/20 p-3">
      <div className="flex items-center gap-2 mb-2">
        <span aria-hidden>✨</span>
        <p className="text-[10px] uppercase tracking-widest text-violet-700 dark:text-violet-300 flex-1">
          AI viz suggestions
        </p>
        {suggestQ.data?.domain && (
          <span className="text-[10px] text-violet-700 dark:text-violet-300 italic">
            looks like: {suggestQ.data.domain}
          </span>
        )}
        {(suggestQ.data || suggestQ.isFetching) && (
          <button
            type="button"
            onClick={() => suggestQ.refetch()}
            disabled={suggestQ.isFetching}
            title="Re-ask the LLM"
            className="text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            {suggestQ.isFetching ? "…" : "↻"}
          </button>
        )}
      </div>

      {!shouldFetch && !suggestQ.isFetching && !suggestQ.data && (
        <button
          type="button"
          onClick={() => setShouldFetch(true)}
          className="w-full text-left px-2 py-1.5 rounded-md text-sm bg-white/60 dark:bg-violet-950/30 hover:bg-white dark:hover:bg-violet-900/40 border border-violet-200/60 dark:border-violet-700/40 transition-colors flex items-center gap-2"
        >
          <span aria-hidden>✨</span>
          <span className="flex-1">
            {nodeLabel
              ? "Suggest visualizations for this step's output"
              : "Suggest visualizations for this dataset"}
          </span>
          <span className="text-[10px] text-muted-foreground">~2s</span>
        </button>
      )}

      {suggestQ.isFetching && (
        <div className="px-2 py-3">
          <PositiveLoaderInline
            variant="thinking"
            size="sm"
            text="Looking at the columns, project name, and inferring domain…"
          />
        </div>
      )}

      {suggestQ.error && (
        <div className="flex items-start gap-2 px-2 py-1.5">
          <p className="text-[11px] text-rose-600 dark:text-rose-400 flex-1">
            {suggestQ.error instanceof ApiError
              ? suggestQ.error.message
              : (suggestQ.error as Error).message}
          </p>
          <button
            type="button"
            onClick={() => suggestQ.refetch()}
            className="shrink-0 text-[10px] px-2 py-0.5 rounded bg-violet-600 hover:bg-violet-700 text-white transition-colors"
          >
            ↻ Retry
          </button>
        </div>
      )}

      <AnimatePresence>
        {suggestQ.data && suggestQ.data.suggestions.length > 0 && (
          <motion.ul
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-1.5"
          >
            {suggestQ.data.suggestions.map((s, i) => {
              const m = stepById[s.step_id];
              if (!m) return null;
              return (
                <motion.li
                  key={`${s.step_id}-${i}`}
                  initial={{ opacity: 0, y: -2 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.04 * i }}
                  className="rounded-md bg-white/70 dark:bg-violet-950/40 border border-violet-200/60 dark:border-violet-700/40 p-2"
                >
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium leading-tight">
                        {s.title || m.label}
                      </p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        {m.label}
                      </p>
                      {s.why && (
                        <p className="text-[11px] text-foreground/80 mt-1.5 leading-snug">
                          {s.why}
                        </p>
                      )}
                      {Object.keys(s.params).length > 0 && (
                        <p className="text-[10px] font-mono text-muted-foreground mt-1.5 truncate">
                          {Object.entries(s.params)
                            .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
                            .join(" · ")}
                        </p>
                      )}
                    </div>
                    <span
                      className={[
                        "shrink-0 text-[9px] px-1.5 py-0.5 rounded-full",
                        CONF_PILL[s.confidence],
                      ].join(" ")}
                    >
                      {s.confidence}
                    </span>
                  </div>
                  <div className="flex justify-end mt-1.5">
                    <button
                      type="button"
                      onClick={() => onApply(m, s.params)}
                      className="text-[11px] px-2 py-0.5 rounded bg-violet-600 hover:bg-violet-700 text-white transition-colors"
                    >
                      ✓ Apply
                    </button>
                  </div>
                </motion.li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>

      {suggestQ.data && suggestQ.data.suggestions.length === 0 && (
        <div className="px-2 py-1.5 space-y-1">
          {suggestQ.data.reason ? (
            <>
              <p className="text-[11px] text-muted-foreground italic">
                🤔 No suitable domain or visualization identified.
              </p>
              <p className="text-[10px] text-muted-foreground/80 leading-snug">
                The model couldn&apos;t infer a confident topic from these column
                names + sample values. Try renaming columns to more descriptive
                terms, or click ↻ to re-ask.
              </p>
            </>
          ) : (
            <p className="text-[11px] text-muted-foreground italic">
              Nothing chartable jumped out — try installing the diagnostic_charts
              or business_charts pack for more options.
            </p>
          )}
        </div>
      )}

      {suggestQ.data?.model && (
        <p className="text-[9px] text-muted-foreground/70 mt-2 text-right">
          via {suggestQ.data.model}
        </p>
      )}
    </div>
  );
}

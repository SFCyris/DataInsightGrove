"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import {
  aiApi,
  ApiError,
  type AiPipelineRoute,
  type AiPipelineStepSuggestion,
  type StepManifest,
} from "@/lib/api/client";
import { PositiveLoaderInline } from "@/components/positive-loader";

/**
 * AI step suggestor — multi-step transform routes for the focused
 * dataset. Click-to-fetch, like ExplainDataset and AiVizHints. Each
 * route is a chain of 1-4 transform steps the LLM thinks would yield
 * an interesting derived dataset (vectorize→similarity, parse→
 * resample→forecast, …).
 *
 * "Apply route" inserts ALL of the route's steps into the pipeline in
 * order, chaining them so step N feeds into step N+1. The parent
 * (pipeline page) handles insertion via the shared `insertStepAfter`
 * helper.
 */
interface Props {
  /** Pipeline whose document supplies the project name + sampling config. */
  pipelineId: string;
  /** Id of the focused node — dataset alias OR step output id.
   *  When this is a step, the AI works on the step's actual output
   *  (sampled) and applying a route mid-pipeline branches off it. */
  nodeId: string;
  /** Optional human-readable label for the focused node. */
  nodeLabel?: string;
  steps: StepManifest[];
  onApplyRoute: (steps: AiPipelineStepSuggestion[]) => void;
}

const CONF_PILL: Record<AiPipelineRoute["confidence"], string> = {
  high: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  low: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

export function AiSuggestSteps({ nodeId, pipelineId, nodeLabel, steps, onApplyRoute }: Props) {
  const cfgQ = useQuery({
    queryKey: ["ai", "config"],
    queryFn: aiApi.config,
    staleTime: 60_000,
  });

  const [shouldFetch, setShouldFetch] = useState(false);
  const [goal, setGoal] = useState("");

  const suggestQ = useQuery({
    queryKey: ["ai", "suggest-pipeline-steps", pipelineId, nodeId, goal],
    queryFn: () =>
      aiApi.suggestPipelineSteps({
        pipeline_id: pipelineId,
        node_id: nodeId,
        goal: goal.trim() || null,
      }),
    enabled: shouldFetch && !!cfgQ.data?.enabled,
    staleTime: 60 * 60_000,
    retry: false,
  });

  if (!cfgQ.data?.enabled) return null;

  const stepById: Record<string, StepManifest> = {};
  for (const s of steps) stepById[s.id] = s;

  return (
    <div className="mb-3 rounded-lg border border-emerald-200/60 dark:border-emerald-800/50 bg-gradient-to-br from-emerald-50/60 to-teal-50/30 dark:from-emerald-950/30 dark:to-teal-950/20 p-3">
      <div className="flex items-center gap-2 mb-2">
        <span aria-hidden>🛤</span>
        <p className="text-[10px] uppercase tracking-widest text-emerald-700 dark:text-emerald-300 flex-1">
          AI step suggestions
        </p>
        {suggestQ.data?.domain && suggestQ.data.routes.length > 0 && (
          <span className="text-[10px] text-emerald-700 dark:text-emerald-300 italic">
            for: {suggestQ.data.domain}
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
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setShouldFetch(true)}
            className="w-full text-left px-2 py-1.5 rounded-md text-sm bg-white/60 dark:bg-emerald-950/30 hover:bg-white dark:hover:bg-emerald-900/40 border border-emerald-200/60 dark:border-emerald-700/40 transition-colors flex items-center gap-2"
          >
            <span aria-hidden>🛤</span>
            <span className="flex-1">
              {nodeLabel
                ? "Suggest transform routes from this step (branches off if applied)"
                : "Suggest transform routes for this dataset"}
            </span>
            <span className="text-[10px] text-muted-foreground">~3s</span>
          </button>
          <details className="text-[10px] text-muted-foreground">
            <summary className="cursor-pointer hover:text-foreground">
              Optional: tell the AI what you want to discover…
            </summary>
            <input
              type="text"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. find groups of similar records"
              className="mt-1.5 w-full rounded-md border border-emerald-200/60 dark:border-emerald-700/40 bg-white/60 dark:bg-emerald-950/30 px-2 py-1 text-[11px] outline-none focus:border-emerald-400"
            />
          </details>
        </div>
      )}

      {suggestQ.isFetching && (
        <div className="px-2 py-3">
          <PositiveLoaderInline
            variant="thinking"
            size="sm"
            text="Looking at the schema and proposing transform routes…"
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
            className="shrink-0 text-[10px] px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white transition-colors"
          >
            ↻ Retry
          </button>
        </div>
      )}

      <AnimatePresence>
        {suggestQ.data && suggestQ.data.routes.length > 0 && (
          <motion.ul
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-1.5"
          >
            {suggestQ.data.routes.map((route, ri) => (
              <motion.li
                key={`route-${ri}`}
                initial={{ opacity: 0, y: -2 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.04 * ri }}
                className="rounded-md bg-white/70 dark:bg-emerald-950/40 border border-emerald-200/60 dark:border-emerald-700/40 p-2.5"
              >
                <div className="flex items-start gap-2 mb-1.5">
                  <p className="text-sm font-medium leading-tight flex-1 min-w-0">
                    {route.title}
                  </p>
                  <span
                    className={[
                      "shrink-0 text-[9px] px-1.5 py-0.5 rounded-full",
                      CONF_PILL[route.confidence],
                    ].join(" ")}
                  >
                    {route.confidence}
                  </span>
                </div>
                {route.why && (
                  <p className="text-[11px] text-foreground/80 mb-1.5 leading-snug">
                    {route.why}
                  </p>
                )}
                <ol className="space-y-1 mb-2">
                  {route.steps.map((s, si) => {
                    const m = stepById[s.step_id];
                    return (
                      <li key={si} className="flex items-start gap-1.5 text-[11px]">
                        <span className="shrink-0 text-emerald-600 dark:text-emerald-400 font-mono">
                          {si + 1}.
                        </span>
                        <div className="flex-1 min-w-0">
                          <span className="font-medium">
                            {m?.label ?? s.step_id}
                          </span>
                          {s.outcome && (
                            <span className="text-muted-foreground"> → {s.outcome}</span>
                          )}
                          {s.rationale && (
                            <p className="text-[10px] text-muted-foreground italic leading-snug mt-0.5">
                              {s.rationale}
                            </p>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => onApplyRoute(route.steps)}
                    className="text-[11px] px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white transition-colors"
                  >
                    ✓ Apply route ({route.steps.length} step{route.steps.length === 1 ? "" : "s"})
                  </button>
                </div>
              </motion.li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>

      {suggestQ.data && suggestQ.data.routes.length === 0 && (
        <p className="text-[11px] text-muted-foreground px-2 py-1.5 italic">
          {suggestQ.data.reason
            ? "🤔 No suitable transform route identified for this dataset."
            : "No routes jumped out — try installing more step packs (ML, time-series) to expand the catalog."}
        </p>
      )}

      {suggestQ.data?.model && (
        <p className="text-[9px] text-muted-foreground/70 mt-2 text-right">
          via {suggestQ.data.model}
        </p>
      )}
    </div>
  );
}

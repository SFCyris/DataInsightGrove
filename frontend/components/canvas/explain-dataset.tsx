"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { aiApi, ApiError } from "@/lib/api/client";
import { PositiveLoaderInline } from "@/components/positive-loader";

/**
 * AI dataset explainer — clickable card in the Hints panel that asks
 * the LLM "what is this dataset and what do its columns represent?".
 *
 * Click-to-fetch (not auto), same as AiVizHints, because it's an LLM
 * call. Result is cached per (datasetId, pipelineId) so navigating
 * away and back doesn't re-prompt.
 *
 * The output has three sections:
 *   1. Narrative — 2-4 sentences on what the dataset represents.
 *   2. Domain pill — one short phrase + confidence indicator.
 *   3. Per-column meanings — name + one-line description, capped at
 *      ~12 columns server-side.
 */
interface Props {
  /** Pipeline whose document supplies the project name + sampling config. */
  pipelineId: string;
  /**
   * Id of the focused node — either a registered dataset's row id or
   * any step output's pipeline-doc id. The backend pulls schema +
   * samples from this node's actual output via the pipeline's chosen
   * sampling method, so the explainer works on derived steps too
   * (post-aggregation, post-filter, etc.).
   *
   * Legacy `datasetId` callers can pass the dataset's id here — the
   * backend treats that as the upstream dataset focus.
   */
  nodeId: string;
  /** Optional human-readable label for the focused node — used as the
   *  card subtitle when explaining a derived step ("Group rows · …"). */
  nodeLabel?: string;
}

const CONF_PILL: Record<"high" | "medium" | "low", string> = {
  high: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  low: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

export function ExplainDataset({ nodeId, pipelineId, nodeLabel }: Props) {
  const cfgQ = useQuery({
    queryKey: ["ai", "config"],
    queryFn: aiApi.config,
    staleTime: 60_000,
  });

  const [shouldFetch, setShouldFetch] = useState(false);

  const explainQ = useQuery({
    queryKey: ["ai", "explain-dataset", pipelineId, nodeId],
    queryFn: () =>
      aiApi.explainDataset({ pipeline_id: pipelineId, node_id: nodeId }),
    enabled: shouldFetch && !!cfgQ.data?.enabled,
    staleTime: 60 * 60_000,
    retry: false,
  });

  if (!cfgQ.data?.enabled) return null;

  return (
    <div className="mb-3 rounded-lg border border-sky-200/60 dark:border-sky-800/50 bg-gradient-to-br from-sky-50/60 to-cyan-50/30 dark:from-sky-950/30 dark:to-cyan-950/20 p-3">
      <div className="flex items-center gap-2 mb-2">
        <span aria-hidden>📖</span>
        <p className="text-[10px] uppercase tracking-widest text-sky-700 dark:text-sky-300 flex-1">
          AI dataset explanation
        </p>
        {explainQ.data?.domain && explainQ.data.confidence !== "low" && (
          <span className="text-[10px] text-sky-700 dark:text-sky-300 italic">
            looks like: {explainQ.data.domain}
          </span>
        )}
        {(explainQ.data || explainQ.isFetching) && (
          <button
            type="button"
            onClick={() => explainQ.refetch()}
            disabled={explainQ.isFetching}
            title="Re-ask the LLM"
            className="text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            {explainQ.isFetching ? "…" : "↻"}
          </button>
        )}
      </div>

      {!shouldFetch && !explainQ.isFetching && !explainQ.data && (
        <button
          type="button"
          onClick={() => setShouldFetch(true)}
          className="w-full text-left px-2 py-1.5 rounded-md text-sm bg-white/60 dark:bg-sky-950/30 hover:bg-white dark:hover:bg-sky-900/40 border border-sky-200/60 dark:border-sky-700/40 transition-colors flex items-center gap-2"
        >
          <span aria-hidden>📖</span>
          <span className="flex-1">
            {nodeLabel
              ? "Explain this step's output (domain + columns)"
              : "Explain this dataset (domain + columns)"}
          </span>
          <span className="text-[10px] text-muted-foreground">~3s</span>
        </button>
      )}

      {explainQ.isFetching && (
        <div className="px-2 py-3">
          <PositiveLoaderInline
            variant="thinking"
            size="sm"
            text="Inferring topic + reading column meanings…"
          />
        </div>
      )}

      {explainQ.error && (
        <div className="flex items-start gap-2 px-2 py-1.5">
          <p className="text-[11px] text-rose-600 dark:text-rose-400 flex-1">
            {explainQ.error instanceof ApiError
              ? explainQ.error.message
              : (explainQ.error as Error).message}
          </p>
          <button
            type="button"
            onClick={() => explainQ.refetch()}
            className="shrink-0 text-[10px] px-2 py-0.5 rounded bg-sky-600 hover:bg-sky-700 text-white transition-colors"
          >
            ↻ Retry
          </button>
        </div>
      )}

      <AnimatePresence>
        {explainQ.data && explainQ.data.narrative && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-2"
          >
            <div className="rounded-md bg-white/70 dark:bg-sky-950/40 border border-sky-200/60 dark:border-sky-700/40 p-2.5">
              <div className="flex items-center gap-2 mb-1.5">
                <p className="text-[11px] font-semibold text-sky-900 dark:text-sky-200 flex-1">
                  {explainQ.data.domain}
                </p>
                <span
                  className={[
                    "text-[9px] px-1.5 py-0.5 rounded-full",
                    CONF_PILL[explainQ.data.confidence],
                  ].join(" ")}
                >
                  {explainQ.data.confidence}
                </span>
              </div>
              <p className="text-[12px] text-foreground/90 leading-relaxed">
                {explainQ.data.narrative}
              </p>
            </div>

            {explainQ.data.columns.length > 0 && (
              <div className="rounded-md bg-white/70 dark:bg-sky-950/40 border border-sky-200/60 dark:border-sky-700/40 p-2.5">
                <p className="text-[10px] uppercase tracking-widest text-sky-700 dark:text-sky-300 mb-1.5">
                  Key columns
                </p>
                <ul className="space-y-1">
                  {explainQ.data.columns.map((c) => (
                    <li key={c.name} className="text-[11px] leading-snug">
                      <span className="font-mono text-sky-900 dark:text-sky-200">
                        {c.name}
                      </span>
                      <span className="text-muted-foreground"> — </span>
                      <span className="text-foreground/85">{c.meaning}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {explainQ.data && !explainQ.data.narrative && (
        <p className="text-[11px] text-muted-foreground px-2 py-1.5 italic">
          {explainQ.data.reason
            ? "🤔 No confident interpretation — column names are too generic for the model to identify a domain."
            : "No confident interpretation."}
        </p>
      )}

      {explainQ.data?.model && (
        <p className="text-[9px] text-muted-foreground/70 mt-2 text-right">
          via {explainQ.data.model}
        </p>
      )}
    </div>
  );
}

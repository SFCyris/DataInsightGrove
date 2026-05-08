"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { RowSample } from "./match-quality";

/**
 * Fetch sampled rows + row count for both upstream inputs of the
 * focused join step. Reuses the same `/preview-step-rows` endpoint
 * the live grid already calls — so when the user has opened the join
 * panel the requested rows are likely already cached by React Query.
 *
 * The backend honours pipeline-level `metadata.sampling`, so the
 * samples the join widgets see for cardinality + match-quality
 * estimates are drawn the way the user expects (e.g. random / stratified
 * / etc.) — not a separate hardcoded head-N. That's the right move:
 * if the user picked stratified-by-status to make rare classes visible,
 * the join's match-quality signal should reflect that same balanced
 * view.
 */
export interface JoinSamplesData {
  leftRows: RowSample[];
  rightRows: RowSample[];
  leftCols: string[];
  rightCols: string[];
  /** Total row count (NOT sample size) — comes from the count(*)
   *  the preview-step-rows endpoint already runs. */
  leftTotal: number;
  rightTotal: number;
  loading: boolean;
  error: string | null;
}

interface Args {
  pipelineId: string;
  leftRef: string | null | undefined;
  rightRef: string | null | undefined;
  /** Bumped on every save — keys the cache so a save invalidates samples. */
  etag: number;
  /** Cap on rows pulled per side. 1000 is plenty for cardinality +
   *  match-quality signals; pulling 50K would just slow the panel
   *  without changing the % bands the colour-coding uses. */
  perSideLimit?: number;
}

export function useJoinSamples(args: Args): JoinSamplesData {
  const limit = args.perSideLimit ?? 1000;
  const leftQ = useQuery({
    queryKey: ["join-sample", args.pipelineId, args.leftRef, args.etag, limit],
    queryFn: () =>
      api.previewStepRows(args.pipelineId, {
        terminal: args.leftRef!,
        sampleRows: limit * 5,
        previewLimit: limit,
      }),
    enabled: !!args.leftRef,
    staleTime: 60_000,
    retry: false,
  });
  const rightQ = useQuery({
    queryKey: ["join-sample", args.pipelineId, args.rightRef, args.etag, limit],
    queryFn: () =>
      api.previewStepRows(args.pipelineId, {
        terminal: args.rightRef!,
        sampleRows: limit * 5,
        previewLimit: limit,
      }),
    enabled: !!args.rightRef,
    staleTime: 60_000,
    retry: false,
  });

  return {
    leftRows: leftQ.data?.rows ?? [],
    rightRows: rightQ.data?.rows ?? [],
    leftCols: (leftQ.data?.columns ?? []).map((c) => c.name),
    rightCols: (rightQ.data?.columns ?? []).map((c) => c.name),
    leftTotal: leftQ.data?.rowCount ?? 0,
    rightTotal: rightQ.data?.rowCount ?? 0,
    loading: leftQ.isLoading || rightQ.isLoading,
    error: (leftQ.error as Error | null)?.message
      ?? (rightQ.error as Error | null)?.message
      ?? null,
  };
}

"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import type { StepManifest } from "@/lib/api/client";

/**
 * ChartDensityWarning — a banner that surfaces ABOVE a chart-step's
 * live preview when the upstream node's row count exceeds the chart
 * kind's recommended sweet spot. Stays hidden when the input fits.
 *
 * Threshold source: the chart step's manifest declares
 * `recommendedMaxRows` (single integer for fixed-kind charts like
 * funnel / pareto / waterfall, or a per-kind map for export_to_image).
 * Values were chosen for visual readability — scatter overplots past
 * 5K, heatmap smears past 50K, etc. New chart kinds inherit this
 * UX automatically by adding the field to their own manifest, no
 * frontend code change required.
 *
 * Remediation:
 *  - 🎲 Sample — inserts a systematic-sampling group_aggregate
 *    upstream of the chart so the user keeps the full pipeline but
 *    previews against a manageable subset.
 *  - Continue — dismisses the banner for this session (the chart
 *    still renders; the user has been informed).
 *
 * Future work: a per-kind aggregate-suggestion (e.g. "Group by [X]"
 * for bar/pareto, "Bin coordinates" for heatmap). For v1 the generic
 * Sample button is the universal answer.
 */
interface Props {
  manifest: StepManifest;
  /** Current params on the focused chart node; used to look up `kind`. */
  params: Record<string, unknown>;
  /** Row count of the upstream node's output. Pulled from the live
   *  grid's last preview metadata. */
  upstreamRowCount: number;
  /** Triggered when the user clicks "Sample" — parent should insert
   *  the systematic-sample step upstream of the chart. */
  onSample: () => void;
  /** Triggered when the user dismisses; banner hides for this session. */
  onDismiss: () => void;
}

/** Resolve the threshold for the focused chart kind. Returns null
 *  when the manifest doesn't declare one (no banner). */
function resolveThreshold(
  manifest: StepManifest,
  params: Record<string, unknown>,
): number | null {
  const r = manifest.recommendedMaxRows;
  if (r == null) return null;
  if (typeof r === "number") return r;
  // Multi-kind: look up the focused `kind` param. Fall back to
  // `_default` if the kind isn't keyed (e.g. user picked a
  // newly-added kind the manifest hasn't catalogued yet).
  const kind = String(params.kind ?? "");
  if (kind && Object.prototype.hasOwnProperty.call(r, kind)) {
    return r[kind];
  }
  if (Object.prototype.hasOwnProperty.call(r, "_default")) {
    return r._default;
  }
  return null;
}

const _NUM_FMT = new Intl.NumberFormat();

export function ChartDensityWarning({
  manifest,
  params,
  upstreamRowCount,
  onSample,
  onDismiss,
}: Props) {
  const threshold = useMemo(
    () => resolveThreshold(manifest, params),
    [manifest, params],
  );

  // Bail early — no threshold OR within the sweet spot.
  if (threshold == null || upstreamRowCount <= threshold) {
    return null;
  }

  const kind =
    typeof manifest.recommendedMaxRows === "object"
      ? String(params.kind ?? "")
      : null;
  const kindLabel = kind && kind !== "auto" ? kind : "this chart";

  return (
    <div
      role="status"
      className="mx-auto mb-3 w-full max-w-md rounded-lg border border-amber-300/70 bg-amber-50/80 dark:border-amber-700/60 dark:bg-amber-950/30 px-3 py-2"
    >
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-base leading-tight">⚠️</span>
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-medium text-amber-900 dark:text-amber-100">
            {_NUM_FMT.format(upstreamRowCount)} rows is dense for {kindLabel}.
          </p>
          <p className="text-[11px] text-amber-800/80 dark:text-amber-200/80 leading-snug mt-0.5">
            Recommended ≤ {_NUM_FMT.format(threshold)}. Past this point the
            picture tends to overplot and the render slows down. Aggregate
            or sample first for a cleaner read.
          </p>
        </div>
      </div>
      <div className="flex justify-end gap-1.5 mt-1.5">
        <Button size="xs" variant="ghost" onClick={onDismiss}>
          Continue
        </Button>
        <Button size="xs" onClick={onSample}>
          🎲 Sample
        </Button>
      </div>
    </div>
  );
}

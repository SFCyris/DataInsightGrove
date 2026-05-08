"use client";

/**
 * CardinalityStrip — top-of-panel summary of the join's row-count
 * consequences. The single most-underrated affordance in a join UI:
 * users who scan it catch "12K became 12M" before clicking Apply,
 * exactly when the cost of fixing is lowest.
 *
 *   left: 50,127       right: 200,043
 *   ▰▰▰▰▰▰▰▰▱▱   ≈ 78% of left rows match
 *   →  result: ~39,099 rows  (1.0× max input)
 *
 * Color rules:
 *   - green: result ≤ max(left, right)         (normal)
 *   - amber: result > max(left, right)         (the join is *expanding* — many-to-many footgun)
 *   - red:   result > max(left, right) × 5     (almost certainly a wrong key)
 *
 * Numbers are sample-on-sample ESTIMATES — clearly labelled. The
 * RATIO is what we colour-code on, since it generalises from sample
 * to full data far better than absolute counts do.
 */
import type { CardinalityEstimate } from "./match-quality";

interface Props {
  estimate: CardinalityEstimate | null;
  /** Total row count from the upstream's preview (not the sample) —
   *  used to label "of N" in the actual size, while the colour-coded
   *  ratio comes from the sample-derived `estimate`. */
  leftTotal: number;
  rightTotal: number;
  loading?: boolean;
}

const _NUM = new Intl.NumberFormat();

export function CardinalityStrip({ estimate, leftTotal, rightTotal, loading }: Props) {
  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-muted/20 px-3 py-2 mb-3 animate-pulse">
        <div className="h-3 w-1/2 rounded bg-muted-foreground/20 mb-1.5" />
        <div className="h-3 w-2/3 rounded bg-muted-foreground/10" />
      </div>
    );
  }
  if (!estimate) {
    return (
      <div className="rounded-lg border border-dashed border-border px-3 py-2 mb-3">
        <p className="text-[11px] text-muted-foreground leading-snug">
          <span aria-hidden>📊</span>{" "}
          <strong>Cardinality preview</strong> — pick at least one key pair below
          to see the estimated row-count impact of this join.
        </p>
      </div>
    );
  }

  const matchPct = Math.round(estimate.matchPct * 100);
  const ratio = estimate.ratio;
  const ratioColor =
    estimate.bucket === "ok"
      ? "text-emerald-700 dark:text-emerald-300 border-emerald-300/60 bg-emerald-50/70 dark:bg-emerald-950/30"
      : estimate.bucket === "expanding"
      ? "text-amber-800 dark:text-amber-200 border-amber-300/70 bg-amber-50/70 dark:bg-amber-950/30"
      : "text-rose-800 dark:text-rose-200 border-rose-400/70 bg-rose-50/70 dark:bg-rose-950/30";
  const ratioBlurb =
    estimate.bucket === "ok"
      ? "result fits within the larger input"
      : estimate.bucket === "expanding"
      ? "result is larger than max input — many-to-many fan-out"
      : "result is far larger than max input — likely wrong key";

  // Bar graphic for match%. 10 segments (▰▱), each = 10%.
  const filled = Math.round(matchPct / 10);
  const bar = "▰".repeat(filled) + "▱".repeat(10 - filled);

  return (
    <div className={`rounded-lg border px-3 py-2 mb-3 space-y-1 ${ratioColor}`}>
      <div className="flex items-center justify-between gap-3 text-[11px]">
        <span className="font-mono">
          left:&nbsp;<strong>{_NUM.format(leftTotal)}</strong>
        </span>
        <span className="font-mono">
          right:&nbsp;<strong>{_NUM.format(rightTotal)}</strong>
        </span>
      </div>
      <div className="flex items-baseline gap-2 text-[11px] font-mono">
        <span aria-hidden className="tracking-tight">{bar}</span>
        <span className="text-[10px]">≈ {matchPct}% of left rows match (sample)</span>
      </div>
      <div className="flex items-baseline gap-2 text-[11px] flex-wrap">
        <span aria-hidden>→</span>
        <span className="font-mono">
          result: <strong>~{_NUM.format(estimate.resultCount)}</strong> rows
        </span>
        <span className="font-mono text-[10px] opacity-80">
          ({ratio.toFixed(2)}× max input)
        </span>
        <span className="text-[10px] italic opacity-90">— {ratioBlurb}</span>
      </div>
    </div>
  );
}

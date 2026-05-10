"use client";

/**
 * InputsPanel — top-of-join surface that names each side's wired source
 * and lets the user rewire / swap inline.
 *
 *   🔌 INPUTS
 *   [L]  📥 customers           5,000 · 5 cols     ▾
 *   [R]  🔀 filtered_orders    30,000 · 4 cols     ▾
 *                                          ↔ swap
 *
 * The dropdown lists EVERY eligible upstream source — every dataset
 * plus every non-descendant node in the pipeline. We deliberately
 * don't filter by "schema-compatible with current keys"; the keys-
 * builder's match-quality bar will warn if the user picks something
 * incompatible. Filtering would hide options the user might want to
 * try (and would also feel mysterious when an option is missing).
 *
 * Wiring changes go through the parent's `onSetInputRef` callback,
 * which decides terminal-mutate vs. mid-chain-branch. Same for
 * `onSwapSides`. This widget is purely presentational about that
 * decision — it always calls the callback and trusts it to do the
 * right thing (and surface a toast when branching).
 */
import type { JoinSamplesData } from "./use-samples";

export interface EligibleSource {
  id: string;
  kind: "dataset" | "node";
  label: string;
}

interface Props {
  leftRef: string | null | undefined;
  rightRef: string | null | undefined;
  eligibleSources: EligibleSource[];
  samples: JoinSamplesData;
  onSetInputRef?: (port: string, newRef: string) => void;
  onSwapSides?: () => void;
}

const SIDE_CHIP: Record<"L" | "R", string> = {
  L: "bg-sky-200/80 text-sky-900 dark:bg-sky-900/50 dark:text-sky-100 ring-1 ring-sky-300/60 dark:ring-sky-700/40",
  R: "bg-emerald-200/80 text-emerald-900 dark:bg-emerald-900/50 dark:text-emerald-100 ring-1 ring-emerald-300/60 dark:ring-emerald-700/40",
};

const SIDE_STRIPE: Record<"L" | "R", string> = {
  L: "bg-sky-400 dark:bg-sky-500",
  R: "bg-emerald-400 dark:bg-emerald-500",
};

function sourceIcon(kind: "dataset" | "node"): string {
  return kind === "dataset" ? "📥" : "🔀";
}

function Row({
  side, currentRef, sources, rowCount, colCount, onChange,
}: {
  side: "L" | "R";
  currentRef: string | null | undefined;
  sources: EligibleSource[];
  rowCount: number | null;
  colCount: number | null;
  onChange?: (newRef: string) => void;
}) {
  const wired = sources.find((s) => s.id === currentRef);
  return (
    <div className="relative flex items-center gap-2 pl-3 pr-2 py-1 rounded-md bg-card/40 hover:bg-card/60 transition-colors">
      <span
        className={[
          "absolute left-0 top-1 bottom-1 w-[3px] rounded-r-sm",
          SIDE_STRIPE[side],
        ].join(" ")}
        aria-hidden="true"
      />
      <span
        className={[
          "shrink-0 inline-flex items-center justify-center min-w-[20px] h-[20px] px-1 rounded text-[10px] font-semibold tabular-nums",
          SIDE_CHIP[side],
        ].join(" ")}
        aria-label={side === "L" ? "Left input" : "Right input"}
      >
        {side}
      </span>
      <span className="shrink-0 text-[14px]" aria-hidden="true">
        {wired ? sourceIcon(wired.kind) : "—"}
      </span>
      <select
        value={currentRef ?? ""}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={!onChange}
        className="flex-1 min-w-0 bg-transparent text-[12px] font-mono px-1 py-0.5 rounded border border-transparent hover:border-border focus:outline-none focus:ring-1 focus:ring-ring/40"
        aria-label={`${side === "L" ? "Left" : "Right"} input source`}
      >
        {!wired && <option value="">— pick a source —</option>}
        {sources.map((s) => (
          <option key={s.id} value={s.id}>
            {sourceIcon(s.kind)} {s.label}
          </option>
        ))}
      </select>
      <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground whitespace-nowrap">
        {rowCount != null ? rowCount.toLocaleString() : "—"}
        {colCount != null ? ` · ${colCount} col${colCount === 1 ? "" : "s"}` : ""}
      </span>
    </div>
  );
}

export function InputsPanel({
  leftRef, rightRef, eligibleSources, samples, onSetInputRef, onSwapSides,
}: Props) {
  const canSwap = !!leftRef && !!rightRef && !!onSwapSides;

  return (
    <div className="rounded-md border border-border/60 bg-card/30 px-3 py-2 space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">
          🔌 Inputs
        </p>
        <button
          type="button"
          onClick={() => onSwapSides?.()}
          disabled={!canSwap}
          title={
            canSwap
              ? "Swap left ↔ right (also flips keys, suffixes, kind, output renames)"
              : "Wire both sides to enable swap"
          }
          className={[
            "text-[10px] px-1.5 py-0.5 rounded-md border transition-colors",
            canSwap
              ? "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground"
              : "border-border/40 text-muted-foreground/40 cursor-not-allowed",
          ].join(" ")}
        >
          ↔ swap sides
        </button>
      </div>
      <div className="space-y-1">
        <Row
          side="L"
          currentRef={leftRef}
          sources={eligibleSources}
          rowCount={leftRef ? samples.leftTotal : null}
          colCount={leftRef ? samples.leftCols.length : null}
          onChange={onSetInputRef ? (r) => onSetInputRef("left", r) : undefined}
        />
        <Row
          side="R"
          currentRef={rightRef}
          sources={eligibleSources}
          rowCount={rightRef ? samples.rightTotal : null}
          colCount={rightRef ? samples.rightCols.length : null}
          onChange={onSetInputRef ? (r) => onSetInputRef("right", r) : undefined}
        />
      </div>
    </div>
  );
}

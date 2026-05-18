"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "motion/react";
import { CATEGORY_EMOJI } from "@/lib/category-emoji";

// ---- Phase A Layer 1: run-state overlay ---------------------------------

export type RunState = "success" | "failed" | "stale" | "never" | "running";

const RUN_STATE_STRIP: Record<RunState, string> = {
  success: "border-t-emerald-500",
  failed:  "border-t-rose-500",
  stale:   "border-t-amber-500",
  never:   "border-t-zinc-300 dark:border-t-zinc-700",
  running: "border-t-sky-500",
};

// ---- Phase A Layer 2: freshness halo ------------------------------------

export type Freshness = "fresh" | "due" | "stale" | "never";

const FRESHNESS_GLYPH: Record<Freshness, string> = {
  fresh:  "🟢",
  due:    "🟡",
  stale:  "🔴",
  never:  "⚪",
};

const FRESHNESS_HALO: Record<Freshness, string> = {
  fresh:  "ring-emerald-300/70 dark:ring-emerald-700/70",
  due:    "ring-amber-300/70 dark:ring-amber-700/70",
  stale:  "ring-rose-300/70 dark:ring-rose-700/70",
  never:  "ring-zinc-200/70 dark:ring-zinc-700/70",
};

// ---- shared ------------------------------------------------------------

function relativeTime(ms: number | null | undefined): string {
  if (ms == null) return "";
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

function formatRows(n: number | null | undefined): string {
  if (n == null) return "";
  if (n < 1_000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

export interface DatasetNodeData extends Record<string, unknown> {
  kind: "dataset";
  label: string;
  connector: string;
  uri: string;
}

export interface StepNodeData extends Record<string, unknown> {
  kind: "step";
  label: string;
  category: string;
  step: string;
  inputPorts: string[];
  outputPorts: string[];
  hasError?: boolean;
  // Phase A Layer 1 — optional run-state overlay. Strip color + clock chip.
  runState?: RunState;
  rowsOut?: number | null;
  finishedAtMs?: number | null;   // epoch ms; relativeTime formats it
  // Phase A Layer 1 — Hex-style inline peek (top 3 rows of step output).
  peek?: { headers: string[]; rows: (string | number | null)[][] };
  // Phase A Layer 2 — freshness halo.
  freshness?: Freshness;
}

export interface OutputNodeData extends Record<string, unknown> {
  kind: "output";
  label: string;
  sink?: string | null;
}

export function DatasetNode({ data, selected }: NodeProps) {
  const d = data as DatasetNodeData;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      className={[
        "min-w-[180px] rounded-lg border bg-card px-3 py-2 shadow-sm",
        selected ? "border-foreground/50 ring-2 ring-ring/40" : "border-border",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="text-base" aria-hidden>📊</span>
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Dataset</p>
          <p className="text-sm font-medium truncate" title={d.label}>{d.label}</p>
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="out" className="!bg-emerald-500/60 hover:!bg-emerald-500 hover:!scale-150 !transition-all !ring-1 !ring-emerald-500/30" />
    </motion.div>
  );
}

export function StepNode({ data, selected }: NodeProps) {
  const d = data as StepNodeData;
  const emoji = CATEGORY_EMOJI[d.category] ?? "🧩";
  // Run-state strip — only when we have last-run data. Falls back to no
  // strip (just the standard border) on never-run nodes if we don't even
  // know they're "never" yet.
  const stripClass = d.runState ? `border-t-2 ${RUN_STATE_STRIP[d.runState]}` : "";
  const haloClass = d.freshness
    ? `ring-2 ring-offset-2 ring-offset-card ${FRESHNESS_HALO[d.freshness]}`
    : "";
  // Relative time chip — rendered when we have a finishedAt.
  const timeAgo = d.finishedAtMs != null
    ? relativeTime(Date.now() - d.finishedAtMs)
    : null;
  const rowsLabel = d.rowsOut != null ? formatRows(d.rowsOut) : null;

  // Round-4 UX#2 finding: the step node had no accessible name; screen
  // readers heard a bare emoji + the category + label crammed
  // together with no semantics. Add an aria-label that reads as
  // "{category} step: {label}, {run-state}" — the latter only
  // appears when relevant so the announcement stays terse.
  const a11yLabel = (() => {
    const parts: string[] = [`${d.category} step: ${d.label}`];
    if (d.runState) parts.push(d.runState);
    if (rowsLabel) parts.push(`${rowsLabel} rows`);
    if (d.hasError) parts.push("error");
    return parts.join(", ");
  })();
  return (
    <motion.div
      role="group"
      aria-label={a11yLabel}
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      className={[
        "min-w-[200px] rounded-lg border bg-card px-3 py-2 shadow-sm",
        stripClass,
        haloClass,
        selected ? "border-foreground/50 ring-2 ring-ring/40" : "border-border",
        d.hasError ? "border-destructive/60" : "",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="text-base" aria-hidden>{emoji}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{d.category}</p>
          <p className="text-sm font-medium truncate">{d.label}</p>
        </div>
        {d.freshness && (
          <span aria-hidden className="text-xs shrink-0" title={`Freshness: ${d.freshness}`}>
            {FRESHNESS_GLYPH[d.freshness]}
          </span>
        )}
        {d.hasError && <span title="Validation error">⚠️</span>}
      </div>

      {(timeAgo || rowsLabel) && (
        <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground tabular-nums">
          {timeAgo && (
            <span className="flex items-center gap-1">
              <span aria-hidden>🕐</span>
              {timeAgo}
            </span>
          )}
          {rowsLabel && (
            <>
              <span aria-hidden>·</span>
              <span>{rowsLabel} rows</span>
            </>
          )}
        </div>
      )}

      {d.peek && d.peek.rows.length > 0 && (
        <div className="mt-2 rounded bg-muted/30 border border-border/40 overflow-hidden">
          <table className="w-full text-[9px] font-mono tabular-nums">
            <thead className="bg-muted/40">
              <tr>
                {d.peek.headers.slice(0, 4).map((h, i) => (
                  <th
                    key={i}
                    className="text-left px-1.5 py-0.5 font-semibold text-muted-foreground/80 truncate"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.peek.rows.slice(0, 3).map((row, ri) => (
                <tr key={ri} className="border-t border-border/30">
                  {row.slice(0, 4).map((cell, ci) => (
                    <td key={ci} className="px-1.5 py-0.5 text-foreground/80 truncate">
                      {cell == null ? "—" : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {d.inputPorts.map((port, idx) => (
        <Handle
          key={`in-${port}`}
          type="target"
          id={port}
          position={Position.Left}
          style={{ top: 24 + idx * 16 }}
          className="!bg-emerald-500/60 hover:!bg-emerald-500 hover:!scale-150 !transition-all !ring-1 !ring-emerald-500/30"
        />
      ))}
      {d.outputPorts.map((port, idx) => (
        <Handle
          key={`out-${port}`}
          type="source"
          id={port}
          position={Position.Right}
          style={{ top: 24 + idx * 16 }}
          className="!bg-emerald-500/60 hover:!bg-emerald-500 hover:!scale-150 !transition-all !ring-1 !ring-emerald-500/30"
        />
      ))}
    </motion.div>
  );
}

export function OutputNode({ data, selected }: NodeProps) {
  const d = data as OutputNodeData;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      className={[
        "min-w-[160px] rounded-lg border-2 border-dashed px-3 py-2",
        selected ? "border-foreground/60 ring-2 ring-ring/40" : "border-border",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="text-base" aria-hidden>📤</span>
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Output</p>
          <p className="text-sm font-medium truncate">{d.label}</p>
        </div>
      </div>
      <Handle type="target" position={Position.Left} id="out" className="!bg-emerald-500/60 hover:!bg-emerald-500 hover:!scale-150 !transition-all !ring-1 !ring-emerald-500/30" />
    </motion.div>
  );
}

// ---- Phase A Layer 4: groups + collapse ---------------------------------

export interface GroupNodeData extends Record<string, unknown> {
  kind: "group";
  label: string;
  childCount: number;
  collapsed: boolean;
  // Aggregated worst-case from children — drives the group's halo strip.
  worstRunState?: RunState;
  worstFreshness?: Freshness;
}

const GROUP_COLOR_BY_FRESHNESS: Record<Freshness, string> = {
  fresh:  "border-emerald-300/70 dark:border-emerald-800/70",
  due:    "border-amber-300/70 dark:border-amber-800/70",
  stale:  "border-rose-300/70 dark:border-rose-800/70",
  never:  "border-zinc-300/70 dark:border-zinc-700/70",
};

/** Dashed-border region drawn BEHIND the group's child step nodes. The
 *  body has `pointerEvents: none` so clicks fall through to step nodes,
 *  but the title chip overrides that — clicking it fires the
 *  onGroupClick callback (wired from the page) to open the edit popover. */
export function GroupNode({ id, data }: NodeProps) {
  const d = data as GroupNodeData & {
    onGroupClick?: (id: string, anchor: { x: number; y: number }) => void;
  };
  const borderClass = d.worstFreshness
    ? GROUP_COLOR_BY_FRESHNESS[d.worstFreshness]
    : "border-zinc-300/60 dark:border-zinc-700/60";
  return (
    <div
      className={[
        "w-full h-full rounded-xl border-2 border-dashed bg-zinc-50/30 dark:bg-zinc-950/30",
        "transition-colors",
        borderClass,
      ].join(" ")}
      style={{ pointerEvents: "none" }}
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
          d.onGroupClick?.(id, { x: r.left, y: r.bottom + 4 });
        }}
        className={[
          "absolute -top-3 left-3 px-2 py-0.5 rounded-md bg-card border border-border shadow-sm",
          "hover:bg-muted hover:border-foreground/30 cursor-pointer transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        ].join(" ")}
        style={{ pointerEvents: "auto" }}
        title="Click to edit group"
      >
        <div className="flex items-center gap-1.5 text-[11px] font-medium">
          <span aria-hidden>📦</span>
          <span className="truncate max-w-[180px]" title={d.label}>{d.label}</span>
          <span className="text-[9px] text-muted-foreground tabular-nums">
            {d.childCount} {d.childCount === 1 ? "node" : "nodes"}
          </span>
          {d.worstFreshness && d.worstFreshness !== "never" && (
            <span aria-hidden className="text-[10px]">
              {d.worstFreshness === "fresh" ? "🟢" : d.worstFreshness === "due" ? "🟡" : "🔴"}
            </span>
          )}
        </div>
      </button>
    </div>
  );
}

export const nodeTypes = {
  dataset: DatasetNode,
  step: StepNode,
  output: OutputNode,
  group: GroupNode,
};

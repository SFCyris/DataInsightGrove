"use client";

import { motion, AnimatePresence } from "motion/react";
import type {
  PipelineDataset,
  PipelineDocument,
  PipelineNode,
  StepManifest,
} from "@/lib/api/client";
import { fmtInt } from "@/lib/format-number";

const CATEGORY_EMOJI: Record<string, string> = {
  ingest: "📥", shape: "✂️", clean: "🧹", derive: "➕",
  combine: "🔗", aggregate: "📊", model: "🧠", output: "📤", custom: "🧩",
};

interface Props {
  doc: PipelineDocument;
  manifests: Record<string, StepManifest>;
  selectedId: string | null;
  /** Map of node id -> row count (for the impact badge) */
  rowCounts: Record<string, number | null>;
  /** Optional per-node compile status from the validate endpoint —
   *  `nodeStatus[id] = { ok, error? }`. Broken nodes render with a red
   *  border + a tooltip showing the humanised error. Undefined entries
   *  mean "unknown / not yet validated" and render as normal. */
  nodeStatus?: Record<string, { ok: boolean; error?: string }>;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onAddStep: (e: React.MouseEvent) => void;
  onRemoveDataset: (id: string) => void;
  /** Optional: handle a right-click on a step pill. */
  onContextMenu?: (id: string, kind: "node" | "dataset", e: React.MouseEvent) => void;
}

// Best-effort SQL → readable label. We only handle the patterns the
// FilterBuilder itself emits; anything fancier renders as raw SQL (truncated).
function readablePredicate(sql: string): string {
  const s = sql.trim();
  // identifier (quoted or bare)
  const idRe = /("([^"]|"")+"|[A-Za-z_][A-Za-z0-9_]*)/.source;
  const stripIdent = (m: string) => (m.startsWith('"') ? m.slice(1, -1).replace(/""/g, '"') : m);
  const stripLit = (lit: string) => {
    const t = lit.trim();
    if (t.startsWith("'") && t.endsWith("'")) return t.slice(1, -1).replace(/''/g, "'");
    return t;
  };
  // Single-condition patterns
  let m: RegExpMatchArray | null;
  if ((m = s.match(new RegExp(`^${idRe}\\s+IS\\s+NOT\\s+NULL$`, "i"))))
    return `${stripIdent(m[1])} is not empty`;
  if ((m = s.match(new RegExp(`^${idRe}\\s+IS\\s+NULL$`, "i"))))
    return `${stripIdent(m[1])} is empty`;
  if ((m = s.match(new RegExp(`^${idRe}\\s*=\\s*(.+)$`))))
    return `${stripIdent(m[1])} is ${stripLit(m[2])}`;
  if ((m = s.match(new RegExp(`^${idRe}\\s*<>\\s*(.+)$`))))
    return `${stripIdent(m[1])} is not ${stripLit(m[2])}`;
  if ((m = s.match(new RegExp(`^${idRe}\\s*>=\\s*(.+)$`))))
    return `${stripIdent(m[1])} ≥ ${stripLit(m[2])}`;
  if ((m = s.match(new RegExp(`^${idRe}\\s*<=\\s*(.+)$`))))
    return `${stripIdent(m[1])} ≤ ${stripLit(m[2])}`;
  if ((m = s.match(new RegExp(`^${idRe}\\s*>\\s*(.+)$`))))
    return `${stripIdent(m[1])} > ${stripLit(m[2])}`;
  if ((m = s.match(new RegExp(`^${idRe}\\s*<\\s*(.+)$`))))
    return `${stripIdent(m[1])} < ${stripLit(m[2])}`;
  if ((m = s.match(new RegExp(`^${idRe}\\s+LIKE\\s+'%([^%']+)%'$`, "i"))))
    return `${stripIdent(m[1])} contains "${m[2]}"`;
  if ((m = s.match(new RegExp(`^${idRe}\\s+LIKE\\s+'([^%']+)%'$`, "i"))))
    return `${stripIdent(m[1])} starts with "${m[2]}"`;
  if ((m = s.match(new RegExp(`^${idRe}\\s+LIKE\\s+'%([^%']+)'$`, "i"))))
    return `${stripIdent(m[1])} ends with "${m[2]}"`;
  // Fall back to the raw SQL (truncated). Better than swallowing it.
  return s.length > 60 ? s.slice(0, 57) + "…" : s;
}

function summarizeParams(node: PipelineNode, manifest: StepManifest | undefined): string {
  const p = node.params;
  if (!p || Object.keys(p).length === 0) return "";
  const id = node.step;
  // Render the predicate in builder vocabulary instead of leaking raw SQL
  // into a UI that promises "no SQL". Multi-cond predicates fall back to SQL.
  if (id === "filter_rows" && typeof p.predicate === "string") return readablePredicate(String(p.predicate));
  if (id === "select_columns" && Array.isArray(p.columns)) return `${p.columns.length} cols`;
  if (id === "rename_columns" && Array.isArray(p.mapping)) return `${p.mapping.length} renames`;
  if (id === "cast_type") return `${p.column} → ${p.targetType}`;
  if (id === "derive_column") return `${p.name} = ${p.expression}`;
  if (id === "sort_rows" && Array.isArray(p.by)) {
    return p.by
      .map((b: { column: string; direction?: string }) => `${b.column} ${(b.direction || "asc").toUpperCase()}`)
      .join(", ");
  }
  if (id === "join") return `${(p.how as string ?? "inner").toUpperCase()} on ${(p.on as Array<{left: string}> ?? []).map((o) => o.left).join(", ") || "?"}`;
  if (id === "union") return p.distinct ? "UNION (distinct)" : "UNION ALL";
  if (id === "group_aggregate") {
    const grp = (p.groupBy as string[] ?? []).join(", ");
    const aggs = (p.aggregates as Array<{ fn: string; column?: string; as?: string }> ?? [])
      .map((a) => `${a.fn}(${a.column ?? "*"})`)
      .join(", ");
    return `by ${grp || "—"} · ${aggs || "—"}`;
  }
  if (id === "pivot_wider") return `${p.names} → ${p.values}`;
  if (id === "pivot_longer" && Array.isArray(p.value_cols)) return `unpivot ${p.value_cols.length}`;
  if (id === "upper_string") return `UPPER(${p.column})`;
  return Object.keys(p).slice(0, 2).map((k) => `${k}=${JSON.stringify(p[k]).slice(0, 14)}`).join(" · ");
}

interface NodeOrDataset {
  kind: "dataset" | "node";
  id: string;
  label: string;
  emoji: string;
  category?: string;
  paramSummary?: string;
  rowCount: number | null;
  selected: boolean;
  /** True when the node has a non-empty `ui.note` — the strip shows a
   *  small 💬 next to the label so users can spot annotated steps at a glance. */
  hasNote?: boolean;
  /** True when the node failed to compile in the most recent validate
   *  (column doesn't exist, bad expression, etc.). The pill renders red
   *  and the tooltip carries the humanised error so the user can act. */
  broken?: boolean;
  /** Humanised error message — title + hint joined. Shown as the pill's
   *  title attribute when broken. */
  brokenReason?: string;
}

export function PipelineStrip({
  doc, manifests, selectedId, rowCounts, nodeStatus, onSelect, onDelete, onAddStep, onRemoveDataset, onContextMenu,
}: Props) {
  const items: NodeOrDataset[] = [];

  // Datasets first (always at the start of the linear strip)
  for (const d of doc.datasets) {
    items.push({
      kind: "dataset",
      id: d.id,
      label: d.label || d.id,
      emoji: "📥",
      rowCount: rowCounts[d.id] ?? null,
      selected: selectedId === d.id,
    });
  }

  // Then nodes — for now, render in topological doc order.
  // (When the user has a branching DAG, the strip linearizes via doc.nodes order;
  //  the canvas view shows the real graph.)
  for (const n of doc.nodes) {
    const manifest = manifests[n.step];
    const status = nodeStatus?.[n.id];
    items.push({
      kind: "node",
      id: n.id,
      label: manifest?.label ?? n.step,
      emoji: CATEGORY_EMOJI[manifest?.category ?? "custom"] ?? "🧩",
      category: manifest?.category,
      paramSummary: summarizeParams(n, manifest),
      rowCount: rowCounts[n.id] ?? null,
      selected: selectedId === n.id,
      hasNote: Boolean((n.ui as { note?: string } | undefined)?.note?.trim()),
      broken: status?.ok === false,
      brokenReason: status?.error,
    });
  }

  return (
    <div className="border-t border-border bg-background/60 backdrop-blur shrink-0">
      <div className="px-3 py-2 flex items-center gap-2 overflow-x-auto">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground shrink-0 mr-1">
          🛤 Steps
        </span>
        {/* mode="sync" + no layout prop on pills:
            previously `mode="popLayout"` + `layout` on every pill caused a
            cascade — every paramSummary edit re-measured the pill, fired a
            spring layout-animation on it, and popLayout propagated springs
            to all following pills. With 15+ steps the editor jankked on
            every keystroke. CSS flex re-layout is instant and the visual
            difference is minimal; we keep enter/exit fade for the new-pill
            appear delight. */}
        <AnimatePresence initial={false} mode="sync">
          {items.map((it, idx) => {
            const prevRows = idx > 0 ? items[idx - 1].rowCount : null;
            const delta =
              prevRows != null && it.rowCount != null && it.kind === "node"
                ? it.rowCount - prevRows
                : null;
            return (
              <motion.div
                key={it.id}
                initial={{ opacity: 0, scale: 0.92 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.92 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="flex items-center gap-1 shrink-0"
              >
                {idx > 0 && (
                  <span className="text-muted-foreground/50 text-xs select-none px-0.5">›</span>
                )}
                {/* Outer pill is a <div role="button"> not a <button> so the
                    inner ✕ button is legal HTML. Without this, React Native /
                    Next 16's hydration validator throws a console error on
                    every mount. We replicate keyboard + click + context-menu
                    semantics manually. */}
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(it.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(it.id);
                    }
                  }}
                  onContextMenu={(e) => {
                    if (onContextMenu) {
                      e.preventDefault();
                      onContextMenu(it.id, it.kind, e);
                    }
                  }}
                  className={[
                    "group relative pl-2 pr-1.5 py-1 rounded-md border text-xs transition-all",
                    "flex items-center gap-1.5 max-w-[260px] cursor-pointer",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
                    // Three states, not mutually exclusive:
                    //   1. selected — bright emerald (the focused step;
                    //      also where a new "Add step" lands)
                    //   2. broken — red ring (compile failed; tooltip carries
                    //      the humanised error)
                    //   3. selected + broken — emerald background, red ring
                    //   4. normal — muted card
                    // Selected colour is intentionally bold so the user
                    // always knows where in the chain they're looking AND
                    // where the next inserted step will land.
                    it.broken && it.selected
                      ? "border-rose-500/70 bg-emerald-100 dark:bg-emerald-500/20 ring-2 ring-rose-500/60"
                      : it.broken
                        ? "border-rose-500/70 bg-rose-50/40 dark:bg-rose-900/20 ring-2 ring-rose-500/40 hover:bg-rose-50/70"
                        : it.selected
                          ? "border-emerald-500/70 bg-emerald-100 dark:bg-emerald-500/20 ring-2 ring-emerald-500/60 shadow-sm"
                          : "border-border bg-card hover:border-foreground/30",
                  ].join(" ")}
                  // Tooltip layering: broken reason wins, then param summary.
                  title={
                    it.broken
                      ? `⚠ ${it.brokenReason ?? "Compile failed"}\n\n${it.paramSummary || ""}`.trim()
                      : it.paramSummary || "Right-click for more"
                  }
                  aria-pressed={it.selected}
                  aria-invalid={it.broken || undefined}
                >
                  <span aria-hidden>{it.emoji}</span>
                  <span className="truncate font-medium">{it.label}</span>
                  {it.broken && (
                    <span
                      className="text-[11px] text-rose-600 dark:text-rose-400"
                      title={it.brokenReason ?? "Compile failed"}
                      aria-label="Step has a compile error"
                    >
                      ⚠
                    </span>
                  )}
                  {it.hasNote && (
                    <span
                      className="text-[10px] text-amber-600 dark:text-amber-400"
                      title="Has a note"
                      aria-label="Has a note"
                    >
                      💬
                    </span>
                  )}
                  {it.paramSummary && (
                    <span className="text-muted-foreground/80 truncate hidden sm:inline">
                      <span className="opacity-50 mx-1">·</span>
                      {it.paramSummary}
                    </span>
                  )}
                  {it.rowCount != null && (
                    <span className="ml-1 text-[10px] tabular-nums text-muted-foreground/80 shrink-0">
                      {fmtInt(it.rowCount)}
                    </span>
                  )}
                  {delta != null && delta !== 0 && (
                    <span
                      className={[
                        "text-[9px] tabular-nums font-semibold shrink-0",
                        delta < 0 ? "text-red-500/80" : "text-emerald-600/80",
                      ].join(" ")}
                    >
                      {delta > 0 ? "+" : ""}{fmtInt(delta)}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (it.kind === "dataset") {
                        onRemoveDataset(it.id);
                      } else {
                        onDelete(it.id);
                      }
                    }}
                    className="ml-1 opacity-0 group-hover:opacity-60 group-focus-within:opacity-60 focus:opacity-100 hover:!opacity-100 hover:text-destructive transition"
                    aria-label="Remove"
                  >
                    ✕
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {/* End-of-strip add button */}
        {items.length > 0 && (
          <span className="text-muted-foreground/50 text-xs select-none px-0.5">›</span>
        )}
        <button
          type="button"
          onClick={onAddStep}
          className="shrink-0 rounded-md border border-dashed border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors"
        >
          ➕ Add step
        </button>

        <span className="flex-1" />
        <span className="text-[10px] text-muted-foreground/60 shrink-0 hidden md:inline">
          Click a step to focus the grid above on its output. ⌘+click a cell to filter.
        </span>
      </div>
    </div>
  );
}

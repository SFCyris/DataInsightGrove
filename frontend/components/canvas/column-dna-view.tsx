"use client";

/**
 * Column DNA computation graph.
 *
 * Bipartite renderer for one target column's full lineage:
 *   - rectangles = data nodes (source columns / derived columns)
 *   - violet chips = op nodes (the transform that produced a column)
 *
 * Read left-to-right: origin source columns → operations → derived
 * columns → more operations → target column. Hover or click any node
 * to light up the ancestry path back to the originating sources; the
 * BreadcrumbCards panel below shows the focused node's formula and
 * inputs in plain prose so users get gestalt + detail in one screen.
 *
 * Combines an expression tree's structural clarity with a Sankey's
 * left-to-right flow.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior } from "d3-zoom";
import { motion, AnimatePresence } from "motion/react";

import { api } from "@/lib/api/client";
import { useURLState, buildShareLink } from "@/lib/use-url-state";

// ---- types ---------------------------------------------------------------

interface LineageNode {
  node_id: string;
  is_dataset: boolean;
  column: string;
  label: string;
  transform: string;
  expression?: string | null;
}
interface LineageEdge {
  from_node_id: string;
  from_column: string;
  to_node_id: string;
  to_column: string;
  transform: string;
}

type DnaKind = "column" | "op" | "source";

interface DnaNode {
  id: string;
  kind: DnaKind;
  label: string;
  origin?: string;     // for source/column nodes: dataset / step display name
  opSymbol?: string;   // for op nodes: visible symbol (×, +, ƒ(x))
  formula?: string;    // for op nodes: plain-English formula
  hint?: string;       // for column nodes: type / range hint
  x: number;
  y: number;
  w: number;
  h: number;
}

interface DnaEdge {
  from: string;
  to: string;
}

// ---- key helpers --------------------------------------------------------

function colKey(nodeId: string, column: string): string {
  return `c:${nodeId}.${column}`;
}
function opKey(nodeId: string, column: string): string {
  return `op:${nodeId}.${column}`;
}

function symbolFor(transform: string): string {
  const t = transform.toLowerCase();
  if (t.includes("aggregate") || t.includes("sum") || t.includes("count") || t.includes("avg")) return "Σ";
  if (t.includes("derive") || t.includes("expression")) return "ƒ(x)";
  if (t.includes("cast")) return "🔄";
  if (t.includes("rename")) return "🏷";
  if (t.includes("coalesce")) return "⊕";
  if (t.includes("group")) return "▢";
  if (t === "passthrough") return "→";
  return "ƒ";
}

// ---- auto-layout --------------------------------------------------------

/** Layout constants.
 *  COL_STRIDE has to leave room for an OP chip + gap on both sides
 *  (gap, op, gap, col, …) — too tight and ops collide with their
 *  neighbouring columns. */
const COL_W = 140;
const COL_H = 56;
const OP_W = 130;
const OP_H = 50;
const COL_STRIDE = 360;         // distance between adjacent column depths
const ROW_H = 92;               // vertical stride between sibling rows
const LEFT_PAD = 24;
const TOP_PAD = 24;

function buildDnaGraph(trace: {
  nodes: LineageNode[];
  edges: LineageEdge[];
  target_node_id: string;
  target_column: string;
}): { nodes: DnaNode[]; edges: DnaEdge[]; width: number; height: number } {
  // BFS depth from sources.
  const adjOut: Record<string, string[]> = {};
  const inDeg: Record<string, number> = {};
  for (const n of trace.nodes) inDeg[colKey(n.node_id, n.column)] = 0;
  for (const e of trace.edges) {
    const from = colKey(e.from_node_id, e.from_column);
    const to = colKey(e.to_node_id, e.to_column);
    (adjOut[from] ??= []).push(to);
    inDeg[to] = (inDeg[to] ?? 0) + 1;
  }
  const depth: Record<string, number> = {};
  const queue: string[] = Object.keys(inDeg).filter((k) => inDeg[k] === 0);
  for (const k of queue) depth[k] = 0;
  while (queue.length > 0) {
    const k = queue.shift()!;
    for (const c of adjOut[k] ?? []) {
      depth[c] = Math.max(depth[c] ?? 0, depth[k] + 1);
      queue.push(c);
    }
  }

  // Group columns by depth.
  const colsByDepth: Record<number, LineageNode[]> = {};
  for (const n of trace.nodes) {
    const d = depth[colKey(n.node_id, n.column)] ?? 0;
    (colsByDepth[d] ??= []).push(n);
  }

  // Group incoming edges per dest column (ALL edges that flow into a
  // single column collapse to one op node).
  const incomingByCol: Record<string, LineageEdge[]> = {};
  for (const e of trace.edges) {
    const k = colKey(e.to_node_id, e.to_column);
    (incomingByCol[k] ??= []).push(e);
  }

  // Op nodes live at depth-0.5 of their target column (midway between
  // their input columns and the dest). Group them by destDepth so we
  // can vertically lay out rows within each "op slot."
  const opsByDepth: Record<number, { destNode: LineageNode; edges: LineageEdge[] }[]> = {};
  for (const [destKey, edges] of Object.entries(incomingByCol)) {
    const destNode = trace.nodes.find((n) => colKey(n.node_id, n.column) === destKey);
    if (!destNode) continue;
    const destDepth = depth[destKey] ?? 0;
    (opsByDepth[destDepth] ??= []).push({ destNode, edges });
  }

  // Vertical layout: for each depth, distribute nodes evenly; ops
  // align with their dest's vertical position.
  const colYByKey: Record<string, number> = {};

  // Stable sort columns by id for deterministic layout.
  for (const dStr of Object.keys(colsByDepth)) {
    colsByDepth[Number(dStr)].sort((a, b) =>
      colKey(a.node_id, a.column).localeCompare(colKey(b.node_id, b.column)),
    );
  }

  // Compute per-depth rows count to size canvas height.
  const allDepths = Object.keys(colsByDepth).map(Number);
  const maxDepth = allDepths.length > 0 ? Math.max(...allDepths) : 0;
  let maxRowsAcrossDepths = 1;
  for (const d of allDepths) {
    maxRowsAcrossDepths = Math.max(maxRowsAcrossDepths, colsByDepth[d].length);
  }

  // Place column nodes.
  const dnaNodes: DnaNode[] = [];
  const targetKey = colKey(trace.target_node_id, trace.target_column);

  for (const d of allDepths) {
    const cols = colsByDepth[d];
    const totalH = cols.length * ROW_H;
    const startY = TOP_PAD + Math.max(0, ((maxRowsAcrossDepths * ROW_H) - totalH) / 2);
    cols.forEach((n, i) => {
      const k = colKey(n.node_id, n.column);
      const y = startY + i * ROW_H;
      colYByKey[k] = y + COL_H / 2;
      const x = LEFT_PAD + d * COL_STRIDE;
      const isTarget = k === targetKey;
      dnaNodes.push({
        id: k,
        kind: n.is_dataset ? "source" : "column",
        label: n.column,
        origin: n.is_dataset ? `📥 ${n.label}` : n.label,
        hint: isTarget ? "target" : undefined,
        x,
        y,
        w: COL_W,
        h: COL_H,
      });
    });
  }

  // Place op nodes between depths. Op vertically aligned with its
  // dest column.
  for (const dStr of Object.keys(opsByDepth)) {
    const d = Number(dStr);
    const ops = opsByDepth[d];
    for (const { destNode, edges } of ops) {
      const opId = opKey(destNode.node_id, destNode.column);
      const destKey = colKey(destNode.node_id, destNode.column);
      const destYCenter = colYByKey[destKey] ?? TOP_PAD + COL_H / 2;
      const x = LEFT_PAD + d * COL_STRIDE - COL_STRIDE / 2 + (COL_W - OP_W) / 2;
      const y = destYCenter - OP_H / 2;
      const sample = edges[0]?.transform ?? "passthrough";
      const sym = symbolFor(sample);
      dnaNodes.push({
        id: opId,
        kind: "op",
        label: sym,
        opSymbol: sym,
        formula: destNode.expression ?? sample,
        x,
        y,
        w: OP_W,
        h: OP_H,
      });
    }
  }

  // Edges: predecessor → op → dest, replacing direct column→column edges.
  const dnaEdges: DnaEdge[] = [];
  for (const [destKey, edges] of Object.entries(incomingByCol)) {
    const destNode = trace.nodes.find((n) => colKey(n.node_id, n.column) === destKey);
    if (!destNode) continue;
    const opId = opKey(destNode.node_id, destNode.column);
    for (const e of edges) {
      const fromKey = colKey(e.from_node_id, e.from_column);
      dnaEdges.push({ from: fromKey, to: opId });
    }
    dnaEdges.push({ from: opId, to: destKey });
  }

  // Canvas dimensions.
  const width = LEFT_PAD * 2 + (maxDepth + 1) * COL_STRIDE - COL_STRIDE / 2;
  const height = TOP_PAD * 2 + maxRowsAcrossDepths * ROW_H + 20;

  return { nodes: dnaNodes, edges: dnaEdges, width, height };
}

// ---- node renderer ------------------------------------------------------

function DnaNodeShape({
  node,
  active,
  onMouseEnter,
  onMouseLeave,
  onClick,
}: {
  node: DnaNode;
  active: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onClick?: () => void;
}) {
  if (node.kind === "op") {
    return (
      <motion.div
        data-dna-node
        initial={false}
        animate={{
          opacity: active ? 1 : 0.92,
          scale: active ? 1.04 : 1,
        }}
        transition={{ duration: 0.2 }}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        onClick={onClick}
        className={[
          "absolute flex items-center justify-center text-center px-2 py-1.5",
          "rounded-md font-mono text-[11px] cursor-pointer select-none",
          "bg-violet-100 dark:bg-violet-950/40 text-violet-900 dark:text-violet-200",
          "border border-violet-300 dark:border-violet-800",
          active ? "shadow-md ring-2 ring-violet-300 dark:ring-violet-700" : "shadow-sm",
        ].join(" ")}
        style={{
          left: node.x,
          top: node.y,
          width: node.w,
          height: node.h,
        }}
      >
        <div className="leading-tight overflow-hidden">
          <div className="text-base font-semibold">{node.opSymbol}</div>
          {node.formula && (
            <div className="text-[9px] opacity-70 mt-0.5 truncate" title={node.formula}>
              {node.formula}
            </div>
          )}
        </div>
      </motion.div>
    );
  }

  const isSource = node.kind === "source";
  return (
    <motion.div
      data-dna-node
      initial={false}
      animate={{
        opacity: active ? 1 : 0.92,
        scale: active ? 1.03 : 1,
      }}
      transition={{ duration: 0.2 }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onClick={onClick}
      className={[
        "absolute rounded-lg cursor-pointer select-none px-2.5 py-1.5 border",
        isSource
          ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-300 dark:border-emerald-800 text-emerald-900 dark:text-emerald-100"
          : "bg-white dark:bg-zinc-900 border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100",
        active
          ? "shadow-lg ring-2 ring-emerald-300 dark:ring-emerald-700"
          : "shadow-sm",
      ].join(" ")}
      style={{
        left: node.x,
        top: node.y,
        width: node.w,
        height: node.h,
      }}
    >
      <div className="flex items-center gap-1.5">
        <span aria-hidden className="text-xs">
          {isSource ? "📥" : "🅰"}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-mono font-semibold truncate" title={node.label}>
            {node.label}
          </div>
          {node.origin && (
            <div className="text-[9px] text-zinc-500 dark:text-zinc-400 truncate" title={node.origin}>
              {node.origin}
            </div>
          )}
          {node.hint && !node.origin && (
            <div className="text-[9px] text-zinc-500 dark:text-zinc-400 truncate font-mono">
              {node.hint}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ---- graph renderer -----------------------------------------------------

type WalkMode = "ancestors" | "descendants" | "both";

function ComputationGraph({
  nodes,
  edges,
  width,
  height,
  activeNodeId,
  onActiveNodeChange,
  walkMode,
}: {
  nodes: DnaNode[];
  edges: DnaEdge[];
  width: number;
  height: number;
  activeNodeId: string | null;
  onActiveNodeChange: (id: string | null) => void;
  walkMode: WalkMode;
}) {
  const byId = useMemo(
    () => Object.fromEntries(nodes.map((n) => [n.id, n])),
    [nodes],
  );

  // Active path: ancestors (where did this come from?), descendants
  // (what does this affect?), or both. The whole point of a DNA view
  // is bidirectional reasoning — restricting to ancestors is just a
  // (defensible) default.
  const activePath = useMemo(() => {
    if (!activeNodeId) return new Set<string>();
    const set = new Set<string>([activeNodeId]);
    if (walkMode === "ancestors" || walkMode === "both") {
      let changed = true;
      while (changed) {
        changed = false;
        for (const e of edges) {
          if (set.has(e.to) && !set.has(e.from)) {
            set.add(e.from);
            changed = true;
          }
        }
      }
    }
    if (walkMode === "descendants" || walkMode === "both") {
      let changed = true;
      while (changed) {
        changed = false;
        for (const e of edges) {
          if (set.has(e.from) && !set.has(e.to)) {
            set.add(e.to);
            changed = true;
          }
        }
      }
    }
    return set;
  }, [activeNodeId, edges, walkMode]);

  // Zoom + pan: d3-zoom on the outer container, transform applied to a
  // single inner wrapper that holds the SVG edges + the absolute-
  // positioned node divs. Filter excludes clicks on `[data-dna-node]`
  // so node hover/click stays untouched.
  const containerRef = useRef<HTMLDivElement>(null);
  const transformRef = useRef<HTMLDivElement>(null);
  const zoomBehaviorRef = useRef<ZoomBehavior<HTMLDivElement, unknown> | null>(null);
  const [zoomScale, setZoomScale] = useState(1);

  useEffect(() => {
    const cnt = containerRef.current;
    const tx = transformRef.current;
    if (!cnt || !tx) return;
    const sel = select(cnt);
    const z = zoom<HTMLDivElement, unknown>()
      .scaleExtent([0.5, 5])
      .filter((event: Event) => {
        if (event.type === "wheel") return true;
        const target = event.target as Element | null;
        if (!target) return false;
        // Don't pan when starting drag on a node (column / op chip).
        if (target.closest("[data-dna-node]")) return false;
        return true;
      })
      .on("zoom", (event) => {
        const t = event.transform;
        tx.style.transform = `translate(${t.x}px, ${t.y}px) scale(${t.k})`;
        tx.style.transformOrigin = "0 0";
        setZoomScale(t.k);
      });
    sel.call(z);
    sel.call(z.transform, zoomIdentity);
    zoomBehaviorRef.current = z;
    return () => {
      sel.on(".zoom", null);
    };
  }, [nodes.length, edges.length]);

  // For button-driven zoom, anchor on the centre of the visible
  // container so the user's mental "look here" stays put. d3-zoom's
  // default for scaleBy is otherwise undefined-anchored and the graph
  // visibly drifts.
  const zoomBy = (factor: number) => {
    const c = containerRef.current;
    const z = zoomBehaviorRef.current;
    if (!c || !z) return;
    const r = c.getBoundingClientRect();
    select(c).call(z.scaleBy, factor, [r.width / 2, r.height / 2]);
  };
  const zoomIn = () => zoomBy(1.4);
  const zoomOut = () => zoomBy(0.71);
  const zoomReset = () => {
    const c = containerRef.current;
    const z = zoomBehaviorRef.current;
    if (c && z) select(c).call(z.transform, zoomIdentity);
  };

  return (
    <div
      ref={containerRef}
      className="relative rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 overflow-hidden cursor-grab active:cursor-grabbing"
      style={{ width: "100%", height: "100%" }}
    >
      {/* Zoom controls — top-right of the canvas. Pointer-events on the
          chip itself; not on the container so panning starts when you
          drag on empty space anywhere else. */}
      <div className="absolute top-2 right-2 z-10 flex items-center rounded border border-zinc-200 dark:border-zinc-800 bg-white/95 dark:bg-zinc-900/95 backdrop-blur shadow-sm overflow-hidden">
        <button
          type="button"
          onClick={zoomOut}
          title="Zoom out (or scroll on the canvas)"
          className="text-xs px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-200 transition-colors"
        >
          −
        </button>
        <span className="text-[10px] font-mono tabular-nums px-2 text-zinc-500 dark:text-zinc-400 border-x border-zinc-200 dark:border-zinc-800 min-w-[42px] text-center select-none">
          {Math.round(zoomScale * 100)}%
        </span>
        <button
          type="button"
          onClick={zoomIn}
          title="Zoom in"
          className="text-xs px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-200 transition-colors"
        >
          +
        </button>
        <button
          type="button"
          onClick={zoomReset}
          title="Reset zoom (fit to default)"
          className="text-xs px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-200 transition-colors border-l border-zinc-200 dark:border-zinc-800"
        >
          ⤢
        </button>
      </div>
      <div
        ref={transformRef}
        className="relative"
        style={{ width, height, minWidth: width, minHeight: height, transformOrigin: "0 0" }}
      >
        {/* dotted background grid */}
        <div
          className="absolute inset-0 opacity-30 dark:opacity-15 pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(circle, rgb(161 161 170) 0.5px, transparent 0.5px)",
            backgroundSize: "16px 16px",
          }}
        />
        <svg
          className="absolute inset-0 pointer-events-none"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
        >
          <defs>
            <marker
              id="dna-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgb(113 113 122)" />
            </marker>
            <marker
              id="dna-arrow-active"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgb(16 185 129)" />
            </marker>
          </defs>
          {edges.map((e, i) => {
            const from = byId[e.from];
            const to = byId[e.to];
            if (!from || !to) return null;
            const x1 = from.x + from.w;
            const y1 = from.y + from.h / 2;
            const x2 = to.x;
            const y2 = to.y + to.h / 2;
            const cx = (x1 + x2) / 2;
            const onPath = activePath.has(e.from) && activePath.has(e.to);
            const dim = activeNodeId != null && !onPath;
            return (
              <motion.path
                key={i}
                initial={false}
                d={`M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`}
                fill="none"
                stroke={onPath ? "rgb(16 185 129)" : "rgb(113 113 122)"}
                strokeWidth={onPath ? 2.2 : 1.4}
                animate={{ opacity: dim ? 0.18 : 1 }}
                transition={{ duration: 0.2 }}
                markerEnd={`url(#${onPath ? "dna-arrow-active" : "dna-arrow"})`}
              />
            );
          })}
        </svg>
        <div className="relative" style={{ width, height }}>
          {nodes.map((n) => (
            <DnaNodeShape
              key={n.id}
              node={n}
              active={
                activeNodeId == null
                  ? false
                  : activePath.has(n.id)
              }
              onMouseEnter={() => onActiveNodeChange(n.id)}
              onMouseLeave={() => onActiveNodeChange(null)}
              onClick={() =>
                onActiveNodeChange(activeNodeId === n.id ? null : n.id)
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- breadcrumb / formula card ------------------------------------------

interface FormulaCardProps {
  active: string | null;
  trace: {
    nodes: LineageNode[];
    edges: LineageEdge[];
    target_node_id: string;
    target_column: string;
  } | null;
  onPick: (k: string) => void;
}

function BreadcrumbCards({ active, trace, onPick }: FormulaCardProps) {
  // Resolve the active node into its formula card (only meaningful for
  // column / source nodes — op nodes themselves don't get a card).
  const card = useMemo(() => {
    if (!active || !trace) return null;
    const isOp = active.startsWith("op:");
    if (isOp) return null;
    const stripped = active.slice(2);
    const dot = stripped.lastIndexOf(".");
    if (dot < 0) return null;
    const nodeId = stripped.slice(0, dot);
    const column = stripped.slice(dot + 1);
    const lineageNode = trace.nodes.find((n) => n.node_id === nodeId && n.column === column);
    if (!lineageNode) return null;

    const inputs = trace.edges.filter((e) => e.to_node_id === nodeId && e.to_column === column);
    const sources = inputs.map((e) => {
      const fromLn = trace.nodes.find((n) => n.node_id === e.from_node_id && n.column === e.from_column);
      const isSource = fromLn?.is_dataset ?? false;
      return {
        col: e.from_column,
        from: isSource ? `📥 ${fromLn?.label ?? e.from_node_id}` : (fromLn?.label ?? e.from_node_id),
        targetKey: colKey(e.from_node_id, e.from_column),
      };
    });

    return {
      col: lineageNode.column,
      formula: lineageNode.expression ?? lineageNode.transform ?? "—",
      origin: lineageNode.is_dataset ? `📥 ${lineageNode.label}` : lineageNode.label,
      isSource: lineageNode.is_dataset,
      sources,
    };
  }, [active, trace]);

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 min-h-[180px]">
      <div className="text-[10px] uppercase tracking-wide text-zinc-400 dark:text-zinc-500 mb-2 font-mono">
        Formula card · drill-down
      </div>
      <AnimatePresence mode="wait">
        {card ? (
          <motion.div
            key={card.col}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.2 }}
          >
            <div className="text-sm">
              <code className="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-900 dark:text-emerald-100 px-1.5 py-0.5 rounded font-mono font-semibold">
                {card.col}
              </code>
              {!card.isSource && card.formula && (
                <>
                  <span className="mx-1.5 text-zinc-400">=</span>
                  <code className="font-mono">{card.formula}</code>
                </>
              )}
              {card.isSource && (
                <>
                  <span className="mx-1.5 text-zinc-400">←</span>
                  <span className="text-zinc-600 dark:text-zinc-300 text-xs">{card.origin}</span>
                </>
              )}
            </div>
            {card.sources.length > 0 && (
              <div className="mt-3 space-y-1">
                <div className="text-[10px] uppercase tracking-wide text-zinc-400 dark:text-zinc-500 font-mono">
                  Inputs
                </div>
                {card.sources.map((s, i) => (
                  <button
                    type="button"
                    key={i}
                    onClick={() => onPick(s.targetKey)}
                    className="w-full text-left flex items-center gap-2 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800/50 rounded px-1.5 py-1 transition-colors"
                  >
                    <code className="font-mono bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                      {s.col}
                    </code>
                    <span className="text-zinc-400">←</span>
                    <span className="text-zinc-600 dark:text-zinc-300">{s.from}</span>
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        ) : (
          <p className="text-xs text-zinc-400 dark:text-zinc-500 italic">
            Hover or click any column / op in the graph above to see its
            formula.
          </p>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---- modal --------------------------------------------------------------

interface Props {
  pipelineId: string;
  nodeId: string;
  column: string;
  onClose: () => void;
}

export function ColumnDNAView({ pipelineId, nodeId, column, onClose }: Props) {
  const [trace, setTrace] = useState<{
    nodes: LineageNode[];
    edges: LineageEdge[];
    target_node_id: string;
    target_column: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // URL-encoded state under `?dna=`. The user can
  // refresh / share / bookmark a specific lineage view (clicked
  // ancestor + walk direction).
  type DNAURLState = { active: string | null; walk: WalkMode };
  const [dnaState, setDnaState] = useURLState<DNAURLState>("dna", {
    active: null,
    walk: "ancestors",
  });
  const activeNode = dnaState.active;
  const setActiveNode = (
    v: string | null | ((p: string | null) => string | null),
  ) =>
    setDnaState((p) => ({
      ...p,
      active: typeof v === "function" ? v(p.active) : v,
    }));
  const walkMode = dnaState.walk;
  const setWalkMode = (v: WalkMode) => setDnaState((p) => ({ ...p, walk: v }));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.getColumnLineage(pipelineId, nodeId, column);
        if (!cancelled) {
          setTrace(res);
          // Default active node = the target column. We respect a
          // URL-decoded value if the user landed via a share link
          // pointing to a specific upstream column — `dnaState.active`
          // is set BEFORE this effect runs (synchronous useState init
          // from URL).
          if (!dnaState.active) {
            setActiveNode(colKey(res.target_node_id, res.target_column));
          }
        }
      } catch (e: unknown) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pipelineId, nodeId, column]);

  // Esc to close.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const graph = useMemo(() => {
    if (!trace) return null;
    return buildDnaGraph(trace);
  }, [trace]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex flex-col"
      onClick={onClose}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="column-dna-title"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        transition={{ type: "spring", stiffness: 320, damping: 28 }}
        className="m-6 flex-1 rounded-xl border border-border bg-card shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-4 py-3 border-b border-border flex items-center gap-3">
          <span aria-hidden className="text-xl">🧬</span>
          <div>
            <p id="column-dna-title" className="text-sm font-semibold leading-tight">Column DNA — computation graph</p>
            <p className="text-[11px] text-muted-foreground font-mono">
              {nodeId} · {column}
            </p>
          </div>
          <span className="flex-1" />
          <span className="text-[11px] text-muted-foreground">
            <span className="hidden md:inline">Hover or click any node · </span>
            <span className="md:hidden">Tap nodes · </span>
            Esc to close
          </span>
          <button
            type="button"
            onClick={async () => {
              await new Promise<void>((r) => setTimeout(r, 220));
              try {
                await navigator.clipboard.writeText(buildShareLink());
              } catch {
                /* clipboard unavailable; silently no-op rather than
                   surface a noisy error inside a modal */
              }
            }}
            title="Copy a link that restores this exact lineage view (active column + walk direction)"
            className="text-xs px-2.5 py-1 rounded hover:bg-muted text-foreground/80 flex items-center gap-1"
          >
            <span aria-hidden>🔗</span> Copy link
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close column DNA"
            className="text-xs px-2.5 py-1 rounded hover:bg-muted text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            ✕
          </button>
        </header>

        {/* legend strip + walk-direction toggle */}
        <div className="px-4 py-2 border-b border-border/60 bg-muted/20 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span>Reading the view:</span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-emerald-100 dark:bg-emerald-900/40 border border-emerald-300 dark:border-emerald-800" />
            📥 origin source column
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700" />
            🅰 derived column
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-violet-100 dark:bg-violet-950/40 border border-violet-300 dark:border-violet-800" />
            op (formula)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-emerald-500 rounded" />
            active path
          </span>
          {/* Walk-direction segmented control. The label changes between
              "where it came from" / "what it affects" / "everything
              connected" so users without lineage-tool background can
              follow what the path is actually showing. */}
          <div className="ml-auto flex items-center gap-2">
            <span className="text-muted-foreground/80">Trace:</span>
            <div className="inline-flex rounded border border-border bg-card overflow-hidden">
              {([
                { id: "ancestors", label: "← upstream", title: "Where this column came from" },
                { id: "both", label: "↔ both", title: "Everything connected to this column" },
                { id: "descendants", label: "downstream →", title: "What this column affects" },
              ] as { id: WalkMode; label: string; title: string }[]).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  title={opt.title}
                  onClick={() => setWalkMode(opt.id)}
                  className={[
                    "text-[10px] px-2 py-0.5 transition-colors",
                    walkMode === opt.id
                      ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-900 dark:text-emerald-100 font-semibold"
                      : "hover:bg-muted text-muted-foreground",
                  ].join(" ")}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex-1 grid grid-rows-[1fr_auto] overflow-hidden">
          <div className="relative p-4 overflow-hidden">
            {!trace && !error && (
              <div className="absolute inset-0 grid place-items-center text-sm text-muted-foreground italic">
                Tracing lineage…
              </div>
            )}
            {error && (
              <div className="absolute inset-0 grid place-items-center text-center text-sm text-rose-600 dark:text-rose-400">
                <div>
                  <div className="text-2xl mb-1" aria-hidden>⚠</div>
                  Could not trace lineage: {error}
                </div>
              </div>
            )}
            {trace && graph && graph.nodes.length === 0 && (
              <div className="absolute inset-0 grid place-items-center text-sm text-muted-foreground italic">
                No upstream lineage — this column is a passthrough source.
              </div>
            )}
            {trace && graph && graph.nodes.length > 0 && (
              <ComputationGraph
                nodes={graph.nodes}
                edges={graph.edges}
                width={graph.width}
                height={graph.height}
                activeNodeId={activeNode}
                onActiveNodeChange={setActiveNode}
                walkMode={walkMode}
              />
            )}
          </div>

          {trace && (
            <div className="px-4 py-3 border-t border-border/60 bg-muted/10">
              <BreadcrumbCards
                active={activeNode}
                trace={trace}
                onPick={(k) => setActiveNode(k)}
              />
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ---- helpers re-exported for external use -----------------------------

export type { LineageNode, LineageEdge };
export { symbolFor };

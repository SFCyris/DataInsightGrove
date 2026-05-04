"use client";

import { useEffect } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type ColumnLineageGraph, type ColumnLineageNode } from "@/lib/api/client";
import { useExpertise } from "@/lib/settings";

interface Props {
  open: boolean;
  pipelineId: string | null;
  nodeId: string | null;
  column: string | null;
  onClose: () => void;
  onJumpToNode?: (nodeId: string) => void;
}

/**
 * Column lineage panel — slide-out drawer that traces a column's ancestry.
 *
 * Beginner: plain narrative ("derived from X, transformed by N steps").
 * Builder:  graph view with click-to-jump.
 * Engineer: + raw expression text inline.
 */
export function LineagePanel({
  open,
  pipelineId,
  nodeId,
  column,
  onClose,
  onJumpToNode,
}: Props) {
  const reduce = useReducedMotion();
  const { isAtLeast } = useExpertise();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const q = useQuery({
    queryKey: ["lineage", pipelineId, nodeId, column],
    queryFn: () =>
      api.getColumnLineage(pipelineId!, nodeId!, column!),
    enabled: open && !!pipelineId && !!nodeId && !!column,
  });

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.aside
            initial={reduce ? { opacity: 0 } : { x: "100%" }}
            animate={reduce ? { opacity: 1 } : { x: 0 }}
            exit={reduce ? { opacity: 0 } : { x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="fixed right-0 top-0 bottom-0 z-50 w-[min(520px,100vw)] bg-background border-l border-border shadow-2xl flex flex-col"
            role="dialog"
            aria-label="Column lineage"
          >
            <header className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/40">
              <span className="text-xl select-none" aria-hidden>🔗</span>
              <div className="flex-1 min-w-0">
                <h2 className="text-sm font-semibold tracking-tight">
                  Lineage of <code className="text-emerald-700 dark:text-emerald-400">{column}</code>
                </h2>
                <p className="text-[10px] text-muted-foreground">
                  Walks back through every step + column that contributed.
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="text-xs text-muted-foreground hover:text-foreground rounded px-2 py-1 hover:bg-muted"
              >
                ✕
              </button>
            </header>

            <div className="flex-1 overflow-y-auto p-4">
              {q.isLoading && (
                <p className="text-sm text-muted-foreground">⏳ Tracing…</p>
              )}
              {q.error && (
                <p className="text-sm text-destructive">
                  Trace failed: {(q.error as Error).message}
                </p>
              )}
              {q.data && (
                <LineageBody
                  data={q.data}
                  showGraph={isAtLeast("builder")}
                  showExpression={isAtLeast("engineer")}
                  onJumpToNode={onJumpToNode}
                />
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function LineageBody({
  data,
  showGraph,
  showExpression,
  onJumpToNode,
}: {
  data: ColumnLineageGraph;
  showGraph: boolean;
  showExpression: boolean;
  onJumpToNode?: (nodeId: string) => void;
}) {
  if (data.nodes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No lineage available. The step may not declare column dependencies yet.
      </p>
    );
  }

  // Build an adjacency view: for each node, list its inbound edges (sources).
  const inboundByTarget = new Map<string, typeof data.edges>();
  for (const e of data.edges) {
    const k = `${e.to_node_id} ${e.to_column}`;
    if (!inboundByTarget.has(k)) inboundByTarget.set(k, []);
    inboundByTarget.get(k)!.push(e);
  }

  // Walk depth-first from the target down to dataset roots.
  const visited = new Set<string>();
  const lines: React.ReactNode[] = [];

  // Iterative depth-first walk — recursion would stack-overflow on a
  // self-referential edge from a buggy step plugin or a very deep DAG.
  // MAX_DEPTH is a final safety so the panel can never hang the editor.
  const MAX_DEPTH = 200;
  const stack: Array<{ nodeId: string; column: string; depth: number }> = [
    { nodeId: data.target_node_id, column: data.target_column, depth: 0 },
  ];
  while (stack.length > 0) {
    const { nodeId, column, depth } = stack.pop()!;
    if (depth > MAX_DEPTH) continue;
    const k = `${nodeId} ${column}`;
    if (visited.has(k)) continue;
    visited.add(k);
    const node = data.nodes.find((n) => n.node_id === nodeId && n.column === column);
    if (!node) continue;
    lines.push(
      <LineageRow
        key={`${k}-${depth}`}
        node={node}
        depth={depth}
        showExpression={showExpression}
        onJumpToNode={onJumpToNode}
      />,
    );
    const inbound = inboundByTarget.get(k) || [];
    // Push in reverse so the first inbound edge is processed first
    // (preserves the previous recursive ordering).
    for (let i = inbound.length - 1; i >= 0; i--) {
      const e = inbound[i];
      stack.push({ nodeId: e.from_node_id, column: e.from_column, depth: depth + 1 });
    }
  }

  return (
    <div>
      <ul className="space-y-1.5">{lines}</ul>
      {showGraph && data.edges.length > 0 && (
        <p className="mt-4 text-[10px] text-muted-foreground">
          Showing {data.nodes.length} node{data.nodes.length === 1 ? "" : "s"} ·{" "}
          {data.edges.length} edge{data.edges.length === 1 ? "" : "s"}.
        </p>
      )}
    </div>
  );
}

function LineageRow({
  node,
  depth,
  showExpression,
  onJumpToNode,
}: {
  node: ColumnLineageNode;
  depth: number;
  showExpression: boolean;
  onJumpToNode?: (nodeId: string) => void;
}) {
  return (
    <li
      className="flex items-start gap-2 text-sm"
      style={{ paddingLeft: `${Math.min(depth * 14, 84)}px` }}
    >
      <span aria-hidden className="text-base mt-0.5 select-none">
        {node.is_dataset ? "📥" : iconForTransform(node.transform)}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="font-medium truncate">{node.label}</span>
          <span className="text-[10px] text-muted-foreground">·</span>
          <code className="text-xs text-emerald-700 dark:text-emerald-400 truncate">
            {node.column}
          </code>
        </div>
        <p className="text-[11px] text-muted-foreground leading-tight">
          {node.transform}
        </p>
        {showExpression && node.expression && (
          <pre className="mt-1 text-[10px] bg-card/50 border border-border rounded px-2 py-1 overflow-auto">
            {node.expression}
          </pre>
        )}
      </div>
      {!node.is_dataset && onJumpToNode && (
        <button
          type="button"
          onClick={() => onJumpToNode(node.node_id)}
          title="Jump to this node in the editor"
          className="text-[10px] text-muted-foreground hover:text-foreground rounded px-1.5 py-0.5 hover:bg-muted"
        >
          ↗
        </button>
      )}
    </li>
  );
}

function iconForTransform(transform: string): string {
  if (transform.startsWith("renamed")) return "🏷";
  if (transform.startsWith("derived")) return "➕";
  if (transform.startsWith("cast")) return "🔄";
  if (transform.startsWith("aggregat")) return "🧮";
  if (transform.startsWith("joined")) return "🔗";
  if (transform === "passthrough") return "→";
  if (transform === "source") return "📥";
  if (transform === "unknown") return "❔";
  return "·";
}

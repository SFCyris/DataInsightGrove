"use client";

/**
 * Cross-pipeline catalog.
 *
 * Workspace-wide meta-graph: each pipeline is a node, edges are inferred
 * from output-sink → dataset-input matches. Same xyflow component used
 * by the in-pipeline canvas, just with a different node-types map and
 * its own auto-layout pass.
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow,
  Handle, Position,
  type Edge as RFEdge, type Node as RFNode, type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion } from "motion/react";

import { catalogApi, searchApi, type CatalogNodeOut, type CatalogEdgeOut } from "@/lib/api/client";
import { useDocumentTitle } from "@/lib/use-document-title";
import { PositiveLoader } from "@/components/positive-loader";

// ---- Pipeline node renderer --------------------------------------------

interface PipelineNodeData extends Record<string, unknown> {
  kind: "pipeline";
  pipeline: CatalogNodeOut;
}

function PipelineNode({ data, selected }: NodeProps) {
  const d = data as PipelineNodeData;
  const p = d.pipeline;
  const stateColor = (() => {
    switch (p.last_run_status) {
      case "succeeded": return "border-t-emerald-500";
      case "failed":    return "border-t-rose-500";
      case "running":   return "border-t-sky-500";
      default:          return "border-t-zinc-300 dark:border-t-zinc-700";
    }
  })();
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      className={[
        "min-w-[220px] rounded-lg border bg-card px-3 py-2 shadow-sm border-t-2",
        stateColor,
        selected ? "ring-2 ring-emerald-400/50" : "",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="text-base" aria-hidden>🌳</span>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Pipeline</p>
          <p className="text-sm font-medium truncate" title={p.name}>{p.name}</p>
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-3 text-[10px] text-muted-foreground tabular-nums">
        <span>{p.node_count} nodes</span>
        {p.group_count > 0 && <span>{p.group_count} groups</span>}
        {p.last_run_status && (
          <span className="font-mono">
            {p.last_run_status === "succeeded" ? "✓" : p.last_run_status === "failed" ? "✗" : "?"} {p.last_run_status}
          </span>
        )}
      </div>
      <Handle type="target" position={Position.Left}  id="in"  className="!bg-foreground/40" />
      <Handle type="source" position={Position.Right} id="out" className="!bg-foreground/40" />
    </motion.div>
  );
}

const nodeTypes = {
  pipeline: PipelineNode,
};

// ---- Auto-layout (simple topological levelizer) ------------------------

function autoLayout(
  nodes: CatalogNodeOut[],
  edges: CatalogEdgeOut[],
): Record<string, { x: number; y: number }> {
  // Compute level = longest path from a source. Lays out nodes in
  // columns by level, rows within a column. Cheap and good enough for
  // <100 pipelines.
  const inDeg: Record<string, number> = {};
  const childrenOf: Record<string, string[]> = {};
  for (const n of nodes) {
    inDeg[n.id] = 0;
    childrenOf[n.id] = [];
  }
  for (const e of edges) {
    inDeg[e.to_id] = (inDeg[e.to_id] ?? 0) + 1;
    (childrenOf[e.from_id] ??= []).push(e.to_id);
  }
  const level: Record<string, number> = {};
  const queue: string[] = nodes.filter((n) => inDeg[n.id] === 0).map((n) => n.id);
  for (const id of queue) level[id] = 0;
  while (queue.length > 0) {
    const id = queue.shift()!;
    for (const c of childrenOf[id] ?? []) {
      level[c] = Math.max(level[c] ?? 0, level[id] + 1);
      queue.push(c);
    }
  }
  // Group by level + assign positions.
  const byLevel: Record<number, string[]> = {};
  for (const n of nodes) {
    const lv = level[n.id] ?? 0;
    (byLevel[lv] ??= []).push(n.id);
  }
  const COL_W = 320;
  const ROW_H = 130;
  const out: Record<string, { x: number; y: number }> = {};

  // Round-4 UX-1 #3 fix: when most/all pipelines have no upstream/
  // downstream lineage edges, every node lands at level 0 — the
  // catalog then renders as one single tall column that scrolls off
  // the viewport. Detect that case and wrap level-0 into a grid of
  // ~sqrt(N) columns so independent pipelines spread across the
  // canvas instead of collapsing into a stripe. Only applies to
  // level 0 (the typical "no edges" case); other levels keep the
  // strict topological column.
  for (const lvStr of Object.keys(byLevel)) {
    const lv = Number(lvStr);
    const ids = byLevel[lv];
    const isFlatZeroLevel =
      lv === 0 && Object.keys(byLevel).length === 1 && ids.length > 6;
    if (isFlatZeroLevel) {
      const cols = Math.max(2, Math.ceil(Math.sqrt(ids.length)));
      const rows = Math.ceil(ids.length / cols);
      const totalW = cols * COL_W;
      const totalH = rows * ROW_H;
      const startX = -totalW / 2;
      const startY = -totalH / 2;
      ids.forEach((id, i) => {
        const r = Math.floor(i / cols);
        const c = i % cols;
        out[id] = { x: startX + c * COL_W, y: startY + r * ROW_H };
      });
    } else {
      const totalH = ids.length * ROW_H;
      const startY = -totalH / 2;
      ids.forEach((id, i) => {
        out[id] = { x: lv * COL_W, y: startY + i * ROW_H };
      });
    }
  }
  return out;
}

// ---- Page --------------------------------------------------------------

export default function CatalogPage() {
  useDocumentTitle('Catalog');
  const [selected, setSelected] = useState<CatalogNodeOut | null>(null);
  // Tag filter. Selected tags are intersected: a
  // pipeline must carry every selected tag to remain visible.
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set());

  const q = useQuery({
    queryKey: ["catalog-lineage"],
    queryFn: catalogApi.lineage,
  });
  const tagsQ = useQuery({
    queryKey: ["all-tags"],
    queryFn: searchApi.listTags,
    staleTime: 30_000,
  });

  // Filter pipelines by active tags BEFORE running the layout, so
  // edges to filtered-out pipelines are also dropped + the layout
  // re-flows around the visible subset.
  const filteredData = useMemo(() => {
    if (!q.data) return null;
    if (activeTags.size === 0) return q.data;
    const visible = new Set(
      q.data.nodes
        .filter((n) => {
          const t = new Set(n.tags ?? []);
          for (const need of activeTags) {
            if (!t.has(need)) return false;
          }
          return true;
        })
        .map((n) => n.id),
    );
    return {
      ...q.data,
      nodes: q.data.nodes.filter((n) => visible.has(n.id)),
      edges: q.data.edges.filter(
        (e) => visible.has(e.from_id) && visible.has(e.to_id),
      ),
    };
  }, [q.data, activeTags]);

  const { rfNodes, rfEdges } = useMemo(() => {
    const data = filteredData;
    if (!data) return { rfNodes: [], rfEdges: [] };
    const positions = autoLayout(data.nodes, data.edges);
    const nodes: RFNode[] = data.nodes.map((n) => ({
      id: n.id,
      type: "pipeline",
      position: positions[n.id] ?? { x: 0, y: 0 },
      data: { kind: "pipeline", pipeline: n } as PipelineNodeData,
    }));
    const edges: RFEdge[] = data.edges.map((e, i) => {
      // When the dataset that this edge passes through has a registered
      // schema, count its columns and surface that on the edge label.
      // The whole edge gets a column-aware tooltip so the user can hover
      // and see which columns flow through.
      const colCount = e.columns?.length ?? 0;
      const labelParts: string[] = [];
      if (e.via) labelParts.push(truncatePath(e.via));
      if (colCount > 0) labelParts.push(`→ ${colCount} col${colCount === 1 ? "" : "s"}`);
      // Round-4 QA-1 #2 — self-loops were getting drawn as a zero-length
      // straight segment hidden behind the node, so a pipeline that
      // wrote back to its own source dataset (common ETL pattern)
      // looked indistinguishable from one with no edges. Switching the
      // edge type to "smoothstep" forces xyflow to route a visible
      // arc when source === target. Other edges keep the default
      // type so this fix doesn't disturb the broader layout.
      const isSelfLoop = e.from_id === e.to_id;
      return {
        id: `e${i}-${e.from_id}-${e.to_id}`,
        source: e.from_id,
        target: e.to_id,
        label: labelParts.length > 0 ? labelParts.join("  ·  ") : undefined,
        type: isSelfLoop ? "smoothstep" : undefined,
        style: {
          strokeWidth: colCount > 0 ? 2 : 1.6,
          stroke: isSelfLoop ? "var(--color-amber-500, #f59e0b)" : "var(--color-emerald-500)",
          // Dashed self-loops let the eye pick out the cyclic
          // relationship even when several other edges fan in/out
          // of the same node.
          ...(isSelfLoop ? { strokeDasharray: "5 3" } : {}),
        },
        labelStyle: { fontSize: 10, fontWeight: colCount > 0 ? 600 : 400 },
        // Round-4 UX#3: hard-coded light emerald wash blew out in
        // dark mode. Use the theme card background so the label stays
        // legible in both palettes.
        labelBgStyle: colCount > 0 ? { fill: "var(--color-card)", fillOpacity: 0.95 } : undefined,
        labelBgPadding: [4, 2] as [number, number],
        // Carry the original payload so the side panel can render the
        // column list when the user clicks an edge.
        data: { catalogEdge: e } as { catalogEdge: CatalogEdgeOut },
      };
    });
    return { rfNodes: nodes, rfEdges: edges };
    // Round-4 UX#3 finding: the dep array previously listed only
    // ``q.data``, missing ``filteredData`` / ``activeTags``. The recompute
    // happened today only because the parent passed a fresh ``key=``
    // to the wrapper, masking the bug. Make the dep set explicit so
    // tag-filter changes recompute the layout reliably.
  }, [filteredData]);

  // Selected edge — drives the column-list side panel. We don't reach
  // for context here because xyflow's onEdgeClick already gives us the
  // typed RFEdge, which we widen via its `data.catalogEdge` field.
  const [selectedEdge, setSelectedEdge] = useState<CatalogEdgeOut | null>(null);

  const toggleTag = (t: string) =>
    setActiveTags((cur) => {
      const next = new Set(cur);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  return (
    <main className="flex flex-col h-screen overflow-hidden">
      <header className="px-6 py-3 border-b border-border flex items-center gap-3 shrink-0">
        <Link
          href="/"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          ← Home
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700">·</span>
        <h1 className="text-lg font-semibold tracking-tight flex items-center gap-2">
          <span aria-hidden>🗺</span>
          Catalog
        </h1>
        <p className="text-xs text-muted-foreground">
          Cross-pipeline lineage — every pipeline + the dataset connections between them.
        </p>
        <span className="flex-1" />
        <span className="text-xs text-muted-foreground tabular-nums">
          {filteredData
            ? `${filteredData.nodes.length} pipelines · ${filteredData.edges.length} edges${activeTags.size > 0 ? ` (filtered from ${q.data?.nodes.length ?? 0})` : ""}`
            : "loading…"}
        </span>
      </header>

      {/* Tag filter chips — only render the strip when there's at
          least one tag in the workspace. Click a chip to toggle it
          ON / OFF; multiple selected tags intersect (AND, not OR). */}
      {(tagsQ.data?.tags?.length ?? 0) > 0 && (
        <div className="px-6 py-2 border-b border-border/60 bg-muted/15 flex flex-wrap items-center gap-2 text-[11px]">
          <span className="text-muted-foreground">Filter by tag:</span>
          {tagsQ.data!.tags.map((t) => {
            const active = activeTags.has(t);
            return (
              <button
                key={t}
                type="button"
                onClick={() => toggleTag(t)}
                className={[
                  "px-2 py-0.5 rounded-full border transition-all",
                  active
                    ? "bg-emerald-100 dark:bg-emerald-900/40 border-emerald-300 dark:border-emerald-700 text-emerald-900 dark:text-emerald-100 font-semibold"
                    : "border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground",
                ].join(" ")}
              >
                #{t}
              </button>
            );
          })}
          {activeTags.size > 0 && (
            <button
              type="button"
              onClick={() => setActiveTags(new Set())}
              className="ml-1 text-[10px] text-muted-foreground hover:text-foreground underline underline-offset-2"
            >
              clear
            </button>
          )}
        </div>
      )}

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 relative">
          {q.isLoading && (
            <div className="absolute inset-0 grid place-items-center">
              <PositiveLoader variant="rendering" primary="Loading catalog…" size="md" showTimer={false} />
            </div>
          )}
          {!q.isLoading && q.data && q.data.nodes.length === 0 && (
            <div className="absolute inset-0 grid place-items-center text-center text-sm text-muted-foreground">
              <div className="flex flex-col items-center gap-3">
                <div className="text-3xl" aria-hidden>📭</div>
                <p className="max-w-md">
                  No pipelines yet — the catalog draws lineage between
                  pipelines and the datasets they read or write.
                </p>
                {/* UX-2 IA fix: empty states need an obvious next
                    action. Without these CTAs a new user lands here,
                    sees a blank canvas, and has to guess where to
                    go. */}
                <div className="flex gap-2 pt-1">
                  <a
                    href="/pipelines"
                    className="px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs"
                  >
                    🛤 Create a pipeline
                  </a>
                  <a
                    href="/datasets"
                    className="px-3 py-1.5 rounded-md border border-border hover:bg-muted text-xs"
                  >
                    📊 Add a dataset first
                  </a>
                </div>
              </div>
            </div>
          )}
          {q.data && q.data.nodes.length > 0 && (
            <ReactFlow
              // ``key`` forces a remount when the filtered node-set changes
              // — that triggers ``fitView`` again (it only runs on mount,
              // otherwise the camera stays zoomed to the original full
              // graph and filtered-out nodes leave conspicuous empty
              // gutters that look like the filter "didn't work" — round-3
              // QA finding).
              key={`${rfNodes.length}-${rfNodes.map((n) => n.id).join(",").slice(0, 80)}`}
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              proOptions={{ hideAttribution: true }}
              minZoom={0.2}
              maxZoom={1.6}
              onNodeClick={(_e, n) => {
                const p = q.data?.nodes.find((x) => x.id === n.id);
                setSelected(p ?? null);
                setSelectedEdge(null);
              }}
              onEdgeClick={(_e, edge) => {
                const ce = (edge.data as { catalogEdge?: CatalogEdgeOut } | undefined)?.catalogEdge;
                if (ce) {
                  setSelectedEdge(ce);
                  setSelected(null);
                }
              }}
              onPaneClick={() => { setSelected(null); setSelectedEdge(null); }}
              nodesDraggable={false}
              nodesConnectable={false}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={18}
                size={1}
                color="var(--color-muted-foreground)"
                style={{ opacity: 0.18 }}
              />
              {/* Round-4 UX-1 #2: minimap was a white slab in dark mode
                 because xyflow defaults the bg to white and the node
                 fill to "rgb(240,240,240)" which both blow out against
                 our zinc-950 dark canvas. We now derive every minimap
                 colour from CSS vars that already track the theme, so
                 dark mode shows a faint zinc panel with emerald tint
                 dots that matches the rest of the catalog chrome. */}
              <MiniMap
                pannable
                className="!bg-card !border !border-border !rounded-md"
                maskColor="rgba(0,0,0,0.18)"
                nodeColor={() => "var(--color-emerald-500, #10b981)"}
                nodeStrokeColor="var(--color-border)"
                nodeBorderRadius={4}
              />
              <Controls showInteractive={false} />
            </ReactFlow>
          )}
        </div>

        {/* Side panel for the focused pipeline */}
        {selected && (
          <motion.aside
            initial={{ x: 20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="w-80 shrink-0 border-l border-border bg-card/40 overflow-y-auto"
          >
            <div className="p-4 border-b border-border">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Pipeline</p>
              <h2 className="text-base font-semibold mt-0.5">{selected.name}</h2>
              {selected.description && (
                <p className="text-xs text-muted-foreground mt-1.5">{selected.description}</p>
              )}
              <div className="mt-3">
                <Link
                  href={`/pipelines/${selected.id}`}
                  className="text-xs px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white inline-flex items-center gap-1.5 transition-colors"
                >
                  Open editor →
                </Link>
              </div>
            </div>
            <div className="p-4 space-y-3 text-xs">
              <Stat label="Last run" value={selected.last_run_status ?? "never run"} />
              <Stat label="Steps" value={String(selected.node_count)} />
              <Stat label="Groups" value={String(selected.group_count)} />
              {selected.inputs.length > 0 && (
                <ListBlock label="Reads from" items={selected.inputs} />
              )}
              {selected.outputs.length > 0 && (
                <ListBlock label="Writes to" items={selected.outputs} />
              )}
            </div>
          </motion.aside>
        )}

        {/* Side panel for a focused EDGE — shows the column-level
            payload that flows from one pipeline to the next. */}
        {selectedEdge && (
          <motion.aside
            initial={{ x: 20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="w-80 shrink-0 border-l border-border bg-card/40 overflow-y-auto"
          >
            <div className="p-4 border-b border-border">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Cross-pipeline edge</p>
              <h2 className="text-sm font-semibold mt-0.5">
                {q.data?.nodes.find((n) => n.id === selectedEdge.from_id)?.name ?? selectedEdge.from_id}
                <span className="mx-2 text-muted-foreground">→</span>
                {q.data?.nodes.find((n) => n.id === selectedEdge.to_id)?.name ?? selectedEdge.to_id}
              </h2>
              {selectedEdge.via && (
                <p className="text-[11px] text-muted-foreground mt-1.5 font-mono break-all">{selectedEdge.via}</p>
              )}
            </div>
            <div className="p-4 space-y-3 text-xs">
              {selectedEdge.columns && selectedEdge.columns.length > 0 ? (
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono mb-2">
                    Columns flowing through ({selectedEdge.columns.length})
                  </div>
                  <ul className="space-y-1">
                    {selectedEdge.columns.map((c) => (
                      <li
                        key={c}
                        className="text-xs font-mono px-2 py-1 rounded bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/60 dark:border-emerald-900/60 flex items-center gap-2"
                      >
                        <span aria-hidden className="text-emerald-600 dark:text-emerald-300">→</span>
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-muted-foreground italic">
                  No registered dataset for <code>{selectedEdge.via}</code> — column-level lineage requires the destination URI to be a known DIG dataset.
                </p>
              )}
            </div>
          </motion.aside>
        )}
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono">
        {label}
      </div>
      <div className="text-sm font-medium mt-0.5">{value}</div>
    </div>
  );
}

function ListBlock({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono mb-1">
        {label}
      </div>
      <ul className="space-y-0.5">
        {items.map((p, i) => (
          <li
            key={i}
            className="font-mono text-[11px] truncate text-foreground/80"
            title={p}
          >
            {truncatePath(p)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function truncatePath(p: string, max = 56): string {
  if (p.length <= max) return p;
  const head = p.slice(0, 16);
  const tail = p.slice(p.length - (max - 19));
  return `${head}…${tail}`;
}

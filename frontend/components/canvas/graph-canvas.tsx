"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow,
  type Edge, type EdgeChange, type Node as RFNode, type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { PipelineDocument, StepManifest } from "@/lib/api/client";
import { nodeTypes } from "./nodes";

interface Props {
  doc: PipelineDocument;
  manifests: Record<string, StepManifest>;
  selectedId: string | null;
  rowCounts: Record<string, number | null>;
  onSelect: (id: string | null) => void;
  onUpdateDoc: (next: PipelineDocument) => void;
  onContextMenu?: (id: string, kind: "node" | "dataset", e: React.MouseEvent) => void;
}

/**
 * Pipeline canvas — true graph view. Counterpart to PipelineStrip's linear
 * view. The user toggles between the two via a button in the editor header.
 *
 * Position state: nodes carry their (x, y) in `node.ui` (already part of the
 * persistent pipeline document). When the user drags a node, we patch
 * doc.nodes[i].ui.{x,y} via `onUpdateDoc` so positions persist across reloads.
 *
 * Auto-layout: when a doc has nodes without ui coords, we compute a topological
 * left-to-right layout on first render (cheap; ≤100 nodes in practice).
 */
export function GraphCanvas({
  doc, manifests, selectedId, rowCounts, onSelect, onUpdateDoc, onContextMenu,
}: Props) {
  // ReactFlowInstance is generic over the actual Node/Edge data shapes; we
  // store it loosely-typed via `any` because the inferred generic from our
  // mapped nodes doesn't match the default-Node type the prop expects.
  const flowRef = useRef<any>(null);  // eslint-disable-line @typescript-eslint/no-explicit-any

  // Build RF nodes + edges from the document. Memoized so React Flow
  // doesn't see "different" arrays on every render and re-init layout.
  const { rfNodes, rfEdges } = useMemo(
    () => buildGraph(doc, manifests, rowCounts),
    [doc, manifests, rowCounts],
  );

  // Position handlers: when the user drags a node, patch doc.nodes[i].ui.
  // We dedupe via the change.id and only persist on dragstop to avoid
  // hammering the autosave during the drag.
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      // Apply changes locally to RF state? No — we don't keep separate state;
      // RF treats `nodes` as controlled when we're driving it from `doc`.
      // For drag we need to update the doc.
      const dragEnded = changes.find(
        (c): c is Extract<NodeChange, { type: "position" }> =>
          c.type === "position" && c.dragging === false && c.position != null,
      );
      if (dragEnded) {
        const id = dragEnded.id;
        const pos = dragEnded.position!;
        // Find node or dataset and patch its ui.
        const inNodes = doc.nodes.find((n) => n.id === id);
        if (inNodes) {
          onUpdateDoc({
            ...doc,
            nodes: doc.nodes.map((n) => n.id === id ? {
              ...n,
              ui: { ...(n.ui ?? {}), x: pos.x, y: pos.y },
            } : n),
          });
          return;
        }
        const inDs = doc.datasets.find((d) => d.id === id);
        if (inDs) {
          // Datasets don't have a `ui` slot in the schema yet — we tuck the
          // position into options for persistence.
          const ui = ((inDs.options ?? {}) as Record<string, unknown>)._ui as
            | { x?: number; y?: number } | undefined;
          onUpdateDoc({
            ...doc,
            datasets: doc.datasets.map((d) => d.id === id ? {
              ...d,
              options: { ...(d.options ?? {}), _ui: { ...(ui ?? {}), x: pos.x, y: pos.y } },
            } : d),
          });
        }
      }
    },
    [doc, onUpdateDoc],
  );

  // Edges are derived; deletions on the canvas would amount to deleting the
  // input link on a node — for now we ignore edge changes (no inline editing).
  const onEdgesChange = useCallback((_changes: EdgeChange[]) => { /* noop */ }, []);

  // Selection: clicking a node sets focused id; clicking the pane clears it.
  const onNodeClick = useCallback(
    (_e: React.MouseEvent, node: RFNode) => onSelect(node.id),
    [onSelect],
  );
  const onPaneClick = useCallback(() => onSelect(null), [onSelect]);
  const onNodeContextMenu = useCallback(
    (e: React.MouseEvent, node: RFNode) => {
      e.preventDefault();
      const isDataset = node.type === "dataset";
      onContextMenu?.(node.id, isDataset ? "dataset" : "node", e);
    },
    [onContextMenu],
  );

  // Sync the selection prop into RF's `selected` flag on each node.
  const nodesWithSelection = useMemo(
    () => rfNodes.map((n) => ({ ...n, selected: n.id === selectedId })),
    [rfNodes, selectedId],
  );

  // Fit view once the graph is built.
  useEffect(() => {
    const inst = flowRef.current;
    if (inst && rfNodes.length > 0) {
      // Defer to next frame so React Flow has measured the nodes.
      const t = setTimeout(() => inst.fitView({ padding: 0.2, duration: 280 }), 0);
      return () => clearTimeout(t);
    }
    // Run only when the structural shape changes — not on every position drag.
  }, [rfNodes.length]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="w-full h-full bg-muted/10">
      <ReactFlow
        nodes={nodesWithSelection}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        onNodeContextMenu={onNodeContextMenu}
        onInit={(inst) => { flowRef.current = inst; }}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={1.6}
        defaultEdgeOptions={{
          animated: false,
          style: { strokeWidth: 1.6, stroke: "var(--color-emerald-500)" },
        }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1}
          color="var(--color-muted-foreground)"
          style={{ opacity: 0.18 }}
        />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => {
            if (n.type === "dataset") return "#0ea5e9";
            if (n.type === "output") return "#16a34a";
            return "#10b981";
          }}
          className="!bg-card !border !border-border !rounded-md !shadow-sm"
        />
        <Controls
          showInteractive={false}
          className="!bg-card !border !border-border !rounded-md !shadow-sm [&>button]:!bg-transparent [&>button]:!border-b [&>button]:!border-border [&>button:hover]:!bg-muted"
        />
      </ReactFlow>
    </div>
  );
}

// ---- Doc → graph -----------------------------------------------------------

function buildGraph(
  doc: PipelineDocument,
  manifests: Record<string, StepManifest>,
  rowCounts: Record<string, number | null>,
): { rfNodes: RFNode[]; rfEdges: Edge[] } {
  // Compute auto-layout for any node without persisted (x, y).
  const layout = autoLayout(doc);

  const nodes: RFNode[] = [];
  const edges: Edge[] = [];

  for (const d of doc.datasets) {
    const ui = (((d.options ?? {}) as Record<string, unknown>)._ui as { x?: number; y?: number } | undefined) ?? {};
    const pos = (typeof ui.x === "number" && typeof ui.y === "number")
      ? { x: ui.x, y: ui.y }
      : layout.get(d.id) ?? { x: 0, y: 0 };
    nodes.push({
      id: d.id,
      type: "dataset",
      position: pos,
      data: {
        kind: "dataset",
        label: d.label || d.id,
        connector: d.connector,
        uri: d.uri,
        rowCount: rowCounts[d.id] ?? null,
      },
    });
  }

  for (const n of doc.nodes) {
    const m = manifests[n.step];
    const inputPorts = m?.io.inputs.ports ?? Object.keys(n.inputs ?? { in: null });
    const outputPorts = m?.io.outputs.ports ?? n.outputs ?? ["out"];
    const ui = n.ui ?? {};
    const pos = (typeof ui.x === "number" && typeof ui.y === "number")
      ? { x: ui.x, y: ui.y }
      : layout.get(n.id) ?? { x: 0, y: 0 };

    nodes.push({
      id: n.id,
      type: "step",
      position: pos,
      data: {
        kind: "step",
        label: ui.label ?? m?.label ?? n.step,
        category: m?.category ?? "custom",
        step: n.step,
        inputPorts,
        outputPorts,
      },
    });

    for (const [port, ref] of Object.entries(n.inputs ?? {})) {
      edges.push({
        id: `${ref.ref}.${ref.port ?? "out"}->${n.id}.${port}`,
        source: ref.ref,
        sourceHandle: ref.port ?? "out",
        target: n.id,
        targetHandle: port,
      });
    }
  }

  for (const o of doc.outputs ?? []) {
    const id = `output_${o.id}`;
    nodes.push({
      id,
      type: "output",
      position: layout.get(id) ?? { x: 0, y: 0 },
      data: {
        kind: "output",
        label: o.name,
        sink: o.sink ? `${o.sink.connector}` : null,
      },
    });
    edges.push({
      id: `${o.from.ref}.${o.from.port ?? "out"}->${id}`,
      source: o.from.ref,
      sourceHandle: o.from.port ?? "out",
      target: id,
      targetHandle: "out",
    });
  }

  return { rfNodes: nodes, rfEdges: edges };
}

/**
 * Topological left-to-right layout. Each node's column is its longest path
 * from any source (dataset); rows are assigned greedily within each column.
 * Cheap O(N+E) — fine for the ≤100 node pipelines DIG sees in practice.
 */
function autoLayout(doc: PipelineDocument): Map<string, { x: number; y: number }> {
  const COL_W = 240;
  const ROW_H = 110;
  const cols = new Map<string, number>();

  // Datasets are column 0.
  for (const d of doc.datasets) cols.set(d.id, 0);

  // Steps: depth = 1 + max(depth of inputs).
  // We may need multiple passes if doc.nodes isn't already in topo order.
  let changed = true;
  let pass = 0;
  while (changed && pass < 64) {
    changed = false;
    pass++;
    for (const n of doc.nodes) {
      const incoming = Object.values(n.inputs ?? {}).map((r) => cols.get(r.ref));
      if (incoming.some((d) => d === undefined)) continue;
      const depth = 1 + Math.max(...incoming.map((d) => d ?? 0));
      if (cols.get(n.id) !== depth) {
        cols.set(n.id, depth);
        changed = true;
      }
    }
  }

  // Outputs: column = max(input depth) + 1
  for (const o of doc.outputs ?? []) {
    const id = `output_${o.id}`;
    const inDepth = cols.get(o.from.ref) ?? 0;
    cols.set(id, inDepth + 1);
  }

  // Group ids by column, then assign rows in declaration order.
  const byCol = new Map<number, string[]>();
  for (const [id, c] of cols) {
    const list = byCol.get(c) ?? [];
    list.push(id);
    byCol.set(c, list);
  }

  const out = new Map<string, { x: number; y: number }>();
  for (const [c, ids] of byCol) {
    ids.forEach((id, row) => {
      out.set(id, { x: c * COL_W, y: row * ROW_H });
    });
  }
  return out;
}

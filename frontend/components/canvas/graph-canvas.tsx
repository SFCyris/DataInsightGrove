"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { toast } from "sonner";
import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow,
  type Edge, type EdgeChange, type Node as RFNode, type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { PipelineDocument, StepManifest } from "@/lib/api/client";
import { nodeTypes, type Freshness, type RunState } from "./nodes";

// Stable references — passing inline literals (or new arrays) for these
// props makes xyflow's StoreUpdater fire its layout effect every render,
// which re-syncs internal state, which causes another render, infinite
// loop. Hoist anything that's a new reference per render up here.
const PAN_ON_DRAG: number[] = [1, 2];   // middle/right mouse pan; left = select
const FIT_VIEW_OPTIONS = { padding: 0.2 };
const PRO_OPTIONS = { hideAttribution: true };
const DEFAULT_EDGE_OPTIONS = {
  animated: false,
  style: { strokeWidth: 1.6, stroke: "var(--color-emerald-500)" },
} as const;

// Per-node metrics from the latest run — drives Layer 1 strip + chip.
export interface NodeRunMetrics {
  status: RunState;
  rows_out?: number | null;
  elapsed_ms?: number | null;
  finished_at_ms?: number | null;
}

// Per-node freshness state — drives Layer 2 halo. Computed server-side
// from the freshness policy + last-run timestamp.
export type NodeFreshness = Freshness;

interface Props {
  doc: PipelineDocument;
  manifests: Record<string, StepManifest>;
  selectedId: string | null;
  rowCounts: Record<string, number | null>;
  // Phase A Layer 1 — per-node run metrics from the latest pipeline run.
  // When absent or empty, no run-state strip / clock chip renders.
  nodeMetrics?: Record<string, NodeRunMetrics>;
  // Phase A Layer 2 — per-node freshness state. When absent, no halo.
  nodeFreshness?: Record<string, NodeFreshness>;
  // Phase A Layer 2 — per-group freshness state (when a group declares
  // its own SLA). Overrides the worst-case-from-children halo color.
  groupFreshness?: Record<string, NodeFreshness>;
  // Phase A Layer 3 — column trace. When set, every node NOT in the set
  // dims to ~25% opacity. Null = no tracing active (full opacity).
  tracedNodeIds?: Set<string> | null;
  // Phase A Layer 4 — multi-selection awareness. The page mirrors xyflow's
  // selection state so the floating action bar knows what to group.
  onSelectionChange?: (selectedStepNodeIds: string[]) => void;
  // Click on a group's title chip → edit popover. The page handles state
  // for which group is being edited.
  onGroupClick?: (groupId: string, anchor: { x: number; y: number }) => void;
  // After a node finishes dragging, the page updates group membership
  // based on which group's bbox the new center falls inside. We surface
  // group bboxes via a callback after each render.
  onGroupBboxesChanged?: (
    bboxes: Record<string, { x: number; y: number; w: number; h: number }>,
  ) => void;
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
  doc, manifests, selectedId, rowCounts, nodeMetrics, nodeFreshness,
  groupFreshness, tracedNodeIds, onSelectionChange, onGroupClick,
  onGroupBboxesChanged, onSelect, onUpdateDoc, onContextMenu,
}: Props) {
  // ReactFlowInstance is generic over the actual Node/Edge data shapes; we
  // store it loosely-typed via `any` because the inferred generic from our
  // mapped nodes doesn't match the default-Node type the prop expects.
  const flowRef = useRef<any>(null);  // eslint-disable-line @typescript-eslint/no-explicit-any

  // Build RF nodes + edges from the document. Memoized so React Flow
  // doesn't see "different" arrays on every render and re-init layout.
  const { rfNodes, rfEdges, groupBboxes } = useMemo(
    () =>
      buildGraph(
        doc, manifests, rowCounts, nodeMetrics, nodeFreshness,
        tracedNodeIds, groupFreshness, onGroupClick,
      ),
    [doc, manifests, rowCounts, nodeMetrics, nodeFreshness, tracedNodeIds, groupFreshness, onGroupClick],
  );

  // Surface group bboxes to the page so it can compute drag-end membership.
  // Stash the previous value in a ref + deep-compare so we only fire when
  // bbox values actually change. Without this, useMemo returns a new
  // object every render → effect fires → setGroupBboxes → re-render →
  // infinite loop.
  const prevBboxesRef = useRef<string>("");
  useEffect(() => {
    const sig = JSON.stringify(groupBboxes);
    if (sig === prevBboxesRef.current) return;
    prevBboxesRef.current = sig;
    onGroupBboxesChanged?.(groupBboxes);
  }, [groupBboxes, onGroupBboxesChanged]);

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
          // Phase A Layer 4 — drag-end group membership, nesting-aware.
          // Each node lives as a DIRECT member of at most one group
          // (the deepest one whose bbox encloses it). Transitive
          // membership through ancestors is implicit — we don't list
          // the same node in multiple groups' node_ids.
          const STEP_W = 220, STEP_H = 80;
          const center = { x: pos.x + STEP_W / 2, y: pos.y + STEP_H / 2 };
          const docGroupsLocal = (doc as PipelineDocument & {
            groups?: Array<{
              id: string;
              node_ids?: string[];
              nodeIds?: string[];
              parent_group_id?: string | null;
              parentGroupId?: string | null;
            }>;
          }).groups ?? [];

          // Compute group depth for "deepest enclosing" tie-breaking.
          const childOf: Record<string, string[]> = {};
          for (const g of docGroupsLocal) {
            const pid = g.parent_group_id ?? g.parentGroupId ?? null;
            if (pid) (childOf[pid] ??= []).push(g.id);
          }
          const depthCache: Record<string, number> = {};
          const dOf = (gid: string, seen = new Set<string>()): number => {
            if (seen.has(gid)) return 0;
            seen.add(gid);
            if (depthCache[gid] != null) return depthCache[gid];
            const ks = childOf[gid] ?? [];
            const d = ks.length === 0 ? 0 : 1 + Math.max(...ks.map((c) => dOf(c, seen)));
            depthCache[gid] = d;
            return d;
          };
          for (const g of docGroupsLocal) dOf(g.id);

          // Find every group whose bbox encloses the new center, then
          // pick the one furthest from the root (highest 0-rooted
          // depth from leaves; we want the most-nested = lowest depth
          // value, i.e. closest to a leaf).
          const enclosing = docGroupsLocal.filter((g) => {
            const bbox = groupBboxes[g.id];
            if (!bbox) return false;
            return (
              center.x >= bbox.x && center.x <= bbox.x + bbox.w &&
              center.y >= bbox.y && center.y <= bbox.y + bbox.h
            );
          });
          // Among enclosing groups, pick the one with the SMALLEST
          // depth (= closest to leaf = most nested) since deepth is
          // counted from leaves upward.
          enclosing.sort((a, b) => (depthCache[a.id] ?? 0) - (depthCache[b.id] ?? 0));
          const targetGroupId = enclosing[0]?.id ?? null;

          let groupsChanged = false;
          const nextGroups = docGroupsLocal.map((g) => {
            const memberList = g.node_ids ?? g.nodeIds ?? [];
            const wasMember = memberList.includes(id);
            const shouldBeMember = g.id === targetGroupId;
            if (shouldBeMember && !wasMember) {
              groupsChanged = true;
              return { ...g, node_ids: [...memberList, id] };
            }
            if (!shouldBeMember && wasMember) {
              groupsChanged = true;
              return { ...g, node_ids: memberList.filter((m) => m !== id) };
            }
            return g;
          });

          const updatedDoc: PipelineDocument = {
            ...doc,
            nodes: doc.nodes.map((n) => n.id === id ? {
              ...n,
              ui: { ...(n.ui ?? {}), x: pos.x, y: pos.y },
            } : n),
            ...(groupsChanged
              ? { groups: nextGroups } as Partial<PipelineDocument>
              : {}),
          };
          onUpdateDoc(updatedDoc);
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
    [doc, onUpdateDoc, groupBboxes],
  );

  // Edges are derived; deletions on the canvas would amount to deleting the
  // input link on a node — for now we ignore edge changes (no inline editing).
  const onEdgesChange = useCallback((_changes: EdgeChange[]) => { /* noop */ }, []);

  // Round-6 UX#2 + Round-8 hardening: drag-to-connect was visually
  // present (every node renders `<Handle>`s) but `onConnect` was never
  // wired, so dragging from a handle to another node did nothing. Round
  // 6 wired it; round 8 added cycle detection, output-node targets, and
  // proper port resolution for empty multi-input steps (join, etc.).
  const onConnect = useCallback(
    (params: { source: string; target: string; targetHandle?: string | null; sourceHandle?: string | null }) => {
      if (!params.source || !params.target || params.source === params.target) {
        return;
      }

      // Output-node target → update doc.outputs[i].from rather than a
      // non-existent node.inputs. Output ids in the canvas are prefixed
      // ``output_<id>``; strip the prefix to look up the doc.outputs row.
      if (params.target.startsWith("output_")) {
        const outId = params.target.slice("output_".length);
        const existing = doc.outputs.find((o) => o.id === outId);
        if (!existing) return;
        const nextDoc: PipelineDocument = {
          ...doc,
          outputs: doc.outputs.map((o) =>
            o.id === outId
              ? { ...o, from: { ref: params.source, port: params.sourceHandle || "out" } }
              : o,
          ),
        };
        onUpdateDoc(nextDoc);
        return;
      }

      const targetNode = doc.nodes.find((n) => n.id === params.target);
      if (!targetNode) return;

      // Cycle detection: walk forward from `target` and refuse if we can
      // reach `source` — the new edge would close a cycle.
      const successors = new Map<string, Set<string>>();
      for (const n of doc.nodes) {
        for (const ref of Object.values(n.inputs ?? {})) {
          if (!ref?.ref) continue;
          if (!successors.has(ref.ref)) successors.set(ref.ref, new Set());
          successors.get(ref.ref)!.add(n.id);
        }
      }
      const queue: string[] = [params.target];
      const seen = new Set<string>([params.target]);
      while (queue.length) {
        const node = queue.shift()!;
        if (node === params.source) {
          toast.error("That connection would create a cycle in the pipeline");
          return;
        }
        for (const next of successors.get(node) ?? []) {
          if (!seen.has(next)) {
            seen.add(next);
            queue.push(next);
          }
        }
      }

      // Port selection. Manifest is authoritative for multi-input
      // steps (join → left/right). Preference order:
      //   1. handle ReactFlow gave us (user dragged onto a specific port)
      //   2. first manifest-declared port that is currently empty
      //   3. first manifest-declared port (overwrite existing)
      //   4. universal "in"
      const manifest = manifests[targetNode.step];
      const declared = manifest?.io.inputs.ports ?? [];
      let targetPort = params.targetHandle || "";
      if (!targetPort && declared.length) {
        const existing = targetNode.inputs ?? {};
        targetPort = declared.find((p) => !existing[p]) || declared[0];
      }
      if (!targetPort) {
        targetPort = Object.keys(targetNode.inputs ?? {})[0] || "in";
      }
      const nextInputs = {
        ...(targetNode.inputs || {}),
        [targetPort]: { ref: params.source, port: params.sourceHandle || "out" },
      };
      const nextDoc: PipelineDocument = {
        ...doc,
        nodes: doc.nodes.map((n) =>
          n.id === params.target ? { ...n, inputs: nextInputs } : n,
        ),
      };
      onUpdateDoc(nextDoc);
    },
    [doc, manifests, onUpdateDoc],
  );

  // Selection: clicking a node sets focused id; clicking the pane clears it.
  const onNodeDoubleClick = useCallback(
    (_e: React.MouseEvent, node: RFNode) => {
      // Round-5 W2: double-clicking a ``pipeline:<id>`` sub-pipeline
      // node opens that pipeline in a new tab so the user can drill
      // in without losing place in the parent.
      const data = node.data as { step?: string } | undefined;
      const step = data?.step;
      if (step && step.startsWith("pipeline:")) {
        const sourceId = step.slice("pipeline:".length);
        if (sourceId) {
          window.open(`/pipelines/${sourceId}`, "_blank", "noopener");
        }
      }
    },
    [],
  );
  const onNodeClick = useCallback(
    (_e: React.MouseEvent, node: RFNode) => onSelect(node.id),
    [onSelect],
  );
  const onPaneClick = useCallback(() => onSelect(null), [onSelect]);

  // Stable handler for xyflow's onSelectionChange — without useCallback,
  // a new identity each render would re-run xyflow's internal selection
  // sync layout effect every render → infinite loop.
  const onSelectionChangeStable = useCallback(
    (sel: { nodes?: RFNode[] }) => {
      const stepIds = (sel.nodes ?? [])
        .filter((n) => (n.data as { kind?: string })?.kind === "step")
        .map((n) => n.id);
      onSelectionChange?.(stepIds);
    },
    [onSelectionChange],
  );
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

  // Fit view ONLY on the first non-zero render (when the graph first
  // becomes visible). Round-9 fix: previously this ran on every
  // structural change (adding a step etc.), which yanked the user's
  // pan/zoom mid-edit. A ref tracks "did we already fit?" so the user
  // can drag and zoom freely after first paint.
  const hasFitOnce = useRef(false);
  useEffect(() => {
    const inst = flowRef.current;
    if (inst && rfNodes.length > 0 && !hasFitOnce.current) {
      const t = setTimeout(() => {
        inst.fitView({ padding: 0.2, duration: 280 });
        hasFitOnce.current = true;
      }, 0);
      return () => clearTimeout(t);
    }
  }, [rfNodes.length]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className="w-full h-full bg-muted/10"
      role="application"
      aria-label="Pipeline graph canvas"
    >
      <span className="sr-only">
        Pipeline graph. Tab to traverse nodes; Enter or Space to select;
        Backspace or Delete to remove a selected node or edge.
      </span>
      <ReactFlow
        nodes={nodesWithSelection}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onPaneClick={onPaneClick}
        onNodeContextMenu={onNodeContextMenu}
        onInit={(inst) => { flowRef.current = inst; }}
        // Multi-selection: shift-click adds/removes; rubber-band drag
        // selects a region. The page mirrors the selection so its
        // floating GroupActionBar knows what to group.
        onSelectionChange={onSelectionChangeStable}
        // Round-4 UX#2: wire Backspace/Delete so keyboard users can
        // remove a selected node/edge. ReactFlow translates these
        // keycodes into the same change events `onNodesChange` /
        // `onEdgesChange` already handle, so the page's onUpdateDoc
        // path is exercised through the existing wiring.
        deleteKeyCode={["Backspace", "Delete"]}
        // Default: drag selects a region (xyflow rubber-band). Hold
        // space (or use the trackpad two-finger pan) to pan the canvas.
        selectionOnDrag
        panOnDrag={PAN_ON_DRAG}
        panOnScroll
        multiSelectionKeyCode="Shift"
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        proOptions={PRO_OPTIONS}
        minZoom={0.2}
        maxZoom={1.6}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1}
          color="var(--color-muted-foreground)"
          style={{ opacity: 0.18 }}
        />
        {/* Mini-map for spatial orientation on big graphs. Colors mirror
            the canvas state so a glance reveals "is anything red?" — failures
            and stale freshness pop in saturated red/amber while healthy
            nodes stay calm emerald. Hidden under 6 nodes (small graphs
            don't benefit and the mini-map just steals real estate). */}
        {rfNodes.length >= 6 && (
          <MiniMap
            pannable
            zoomable
            ariaLabel="Pipeline mini-map — drag to pan, scroll to zoom"
            // Round-4 UX#2: previously hard-coded near-white mask
            // colour (``rgba(244,244,245,0.55)``) blew out in dark
            // mode. Use the CSS variable that already tracks the
            // active theme so the mask stays subtle in both modes.
            maskColor="color-mix(in srgb, var(--color-card) 55%, transparent)"
            maskStrokeColor="color-mix(in srgb, var(--color-border) 80%, transparent)"
            maskStrokeWidth={1.5}
            nodeColor={(n) => {
              const d = (n.data ?? {}) as {
                runState?: string;
                freshness?: string;
              };
              if (d.runState === "failed") return "#ef4444";
              if (d.runState === "running") return "#3b82f6";
              if (d.freshness === "stale") return "#f97316";
              if (d.freshness === "due") return "#f59e0b";
              if (d.freshness === "fresh" || d.runState === "succeeded") return "#10b981";
              if (n.type === "dataset") return "#0ea5e9";
              if (n.type === "output") return "#22c55e";
              return "#a1a1aa";
            }}
            nodeStrokeColor={(n) => {
              const d = (n.data ?? {}) as {
                runState?: string;
                freshness?: string;
              };
              if (d.runState === "failed") return "#dc2626";
              if (d.freshness === "stale") return "#ea580c";
              if (d.freshness === "due") return "#d97706";
              return "rgba(15, 23, 42, 0.18)";
            }}
            nodeStrokeWidth={1.5}
            nodeBorderRadius={4}
            // Round-5 W2: clicking a node in the mini-map now selects
            // it in the main canvas. The whole point of seeing a red
            // dot in the minimap on a 30-step pipeline is being able to
            // jump straight there.
            onNodeClick={(_e, n) => onSelect(n.id)}
            className="!bg-card/85 backdrop-blur !border !border-border/70 !rounded-md !shadow-md"
          />
        )}
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
  nodeMetrics?: Record<string, NodeRunMetrics>,
  nodeFreshness?: Record<string, NodeFreshness>,
  tracedNodeIds?: Set<string> | null,
  groupFreshness?: Record<string, NodeFreshness>,
  onGroupClick?: (groupId: string, anchor: { x: number; y: number }) => void,
): {
  rfNodes: RFNode[];
  rfEdges: Edge[];
  groupBboxes: Record<string, { x: number; y: number; w: number; h: number }>;
} {
  // Phase A Layer 3 — node-dim helper. When tracing is active, any node
  // not in the traced set fades dramatically + greyscales. The previous
  // 22% opacity was too subtle — easy to miss the highlight unless you
  // were looking for it. Now off-path nodes drop to 12% AND lose their
  // color (grayscale 80%) so the on-path nodes stand out unambiguously.
  const dimNode = (id: string): React.CSSProperties =>
    tracedNodeIds && !tracedNodeIds.has(id)
      ? {
          opacity: 0.12,
          filter: "grayscale(0.8) blur(0.5px)",
          transition: "opacity 200ms ease, filter 200ms ease",
        }
      : { opacity: 1, transition: "opacity 200ms ease, filter 200ms ease" };
  // Compute auto-layout for any node without persisted (x, y).
  const layout = autoLayout(doc);

  const nodes: RFNode[] = [];
  const edges: Edge[] = [];

  // Phase A Layer 4 — node groups (with nesting support). Each group can
  // declare a parent_group_id; outer group's bbox auto-expands to
  // include child group bboxes so the user can group sub-clusters
  // inside a larger logical region.
  const docGroups = (doc as PipelineDocument & {
    groups?: Array<{
      id: string;
      label: string;
      node_ids?: string[];
      nodeIds?: string[];
      parent_group_id?: string | null;
      parentGroupId?: string | null;
      ui?: { collapsed?: boolean };
    }>;
  }).groups ?? [];
  const childToGroup: Record<string, string> = {};
  for (const g of docGroups) {
    const ids = g.node_ids ?? g.nodeIds ?? [];
    for (const nid of ids) {
      childToGroup[nid] = g.id;
    }
  }

  for (const d of doc.datasets) {
    const ui = (((d.options ?? {}) as Record<string, unknown>)._ui as { x?: number; y?: number } | undefined) ?? {};
    const pos = (typeof ui.x === "number" && typeof ui.y === "number")
      ? { x: ui.x, y: ui.y }
      : layout.get(d.id) ?? { x: 0, y: 0 };
    nodes.push({
      id: d.id,
      type: "dataset",
      position: pos,
      // Initial dimensions for MiniMap visibility (see comment on the
      // step-node push below).
      initialWidth: 200,
      initialHeight: 56,
      data: {
        kind: "dataset",
        label: d.label || d.id,
        connector: d.connector,
        uri: d.uri,
        rowCount: rowCounts[d.id] ?? null,
      },
      style: dimNode(d.id),
    });
  }

  // Pass 1: collect step-node positions so we can compute group bboxes.
  const stepPositions: Record<string, { x: number; y: number; w: number; h: number }> = {};
  for (const n of doc.nodes) {
    const ui = n.ui ?? {};
    const pos = (typeof ui.x === "number" && typeof ui.y === "number")
      ? { x: ui.x, y: ui.y }
      : layout.get(n.id) ?? { x: 0, y: 0 };
    // Approximate node footprint (xyflow doesn't tell us until measured) —
    // 220×80 covers the StepNode w/ run-state strip. Used only for group
    // bbox padding, not for layout precision.
    stepPositions[n.id] = { x: pos.x, y: pos.y, w: 220, h: 80 };
  }

  // Phase A Layer 4 — emit group nodes BEFORE their members so the
  // Bbox computation is RECURSIVE. Order of operations:
  //   1. Topo-sort groups by depth (leaves first — groups with no
  //      child groups, then groups whose only sub-groups are already
  //      computed, etc.).
  //   2. For each group, bbox = bbox of (member step positions ∪
  //      sub-group bboxes), padded for the title chip + breathing room.
  //   3. Emit group nodes into the rfNodes array OUTERMOST-FIRST so
  //      xyflow renders outer groups behind inner ones (xyflow draws in
  //      array order, with later items on top).
  const PAD = 24;
  const TITLE_PAD = 16;
  const NESTED_PAD = 12;        // additional padding when nested, so the
                                // child's title chip has room above it
  const groupBboxes: Record<string, { x: number; y: number; w: number; h: number }> = {};

  // Build a quick parent→children index for the topo sort.
  const childGroupsOf: Record<string, string[]> = {};
  for (const g of docGroups) {
    const parentId = g.parent_group_id ?? g.parentGroupId ?? null;
    if (parentId) {
      (childGroupsOf[parentId] ??= []).push(g.id);
    }
  }

  // Compute depth — distance from the deepest descendant. Groups with no
  // sub-groups have depth 0; groups containing a depth-N group have
  // depth N+1. Used both for bbox-computation order (deepest first)
  // AND for render order (outermost first = highest depth first in
  // node array, so it's drawn first → behind).
  const groupById = new Map(docGroups.map((g) => [g.id, g]));
  const groupDepth: Record<string, number> = {};
  function depthOf(gid: string, seen = new Set<string>()): number {
    if (seen.has(gid)) return 0;     // cycle guard (shouldn't happen)
    seen.add(gid);
    if (groupDepth[gid] != null) return groupDepth[gid];
    const kids = childGroupsOf[gid] ?? [];
    const d = kids.length === 0 ? 0 : 1 + Math.max(...kids.map((c) => depthOf(c, seen)));
    groupDepth[gid] = d;
    return d;
  }
  for (const g of docGroups) depthOf(g.id);

  // Compute bboxes in DEPTH order (lowest depth first = leaves first).
  const groupsByAscendingDepth = [...docGroups].sort(
    (a, b) => (groupDepth[a.id] ?? 0) - (groupDepth[b.id] ?? 0),
  );

  for (const g of groupsByAscendingDepth) {
    const memberStepIds = (g.node_ids ?? g.nodeIds ?? []).filter(
      (id) => stepPositions[id],
    );
    const childGroups = (childGroupsOf[g.id] ?? []).filter(
      (cid) => groupBboxes[cid],
    );
    if (memberStepIds.length === 0 && childGroups.length === 0) continue;

    // Collect all (x, y, w, h) rects to envelope.
    const rects: { x: number; y: number; w: number; h: number }[] = [];
    for (const id of memberStepIds) rects.push(stepPositions[id]);
    for (const cid of childGroups) rects.push(groupBboxes[cid]);

    const xs = rects.map((r) => r.x);
    const ys = rects.map((r) => r.y);
    const xrs = rects.map((r) => r.x + r.w);
    const yrs = rects.map((r) => r.y + r.h);

    // Outer-most groups need a bit more headroom because they wrap a
    // child group whose own title chip is drawn above its top edge.
    const isNested = childGroups.length > 0;
    const verticalTopPad = (isNested ? NESTED_PAD : 0) + PAD + TITLE_PAD;
    const minX = Math.min(...xs) - PAD;
    const minY = Math.min(...ys) - verticalTopPad;
    const maxX = Math.max(...xrs) + PAD;
    const maxY = Math.max(...yrs) + PAD;
    groupBboxes[g.id] = { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  // Emit group nodes in OUTERMOST-FIRST order (highest depth first, so
  // the parent comes before its children in the rfNodes array → xyflow
  // draws the parent behind the children). Step nodes come last (added
  // by the loop below), so they sit on top of everything.
  const groupsByDescendingDepth = [...docGroups].sort(
    (a, b) => (groupDepth[b.id] ?? 0) - (groupDepth[a.id] ?? 0),
  );

  for (const g of groupsByDescendingDepth) {
    const bbox = groupBboxes[g.id];
    if (!bbox) continue;
    const memberStepIds = (g.node_ids ?? g.nodeIds ?? []).filter(
      (id) => stepPositions[id],
    );

    // Aggregations span MEMBER STEPS AND THE STEPS WITHIN SUB-GROUPS too,
    // so a parent group's halo correctly reflects its entire transitive
    // membership. Walk descendants once and union all step ids.
    const transitiveStepIds = new Set<string>(memberStepIds);
    const stack = [...(childGroupsOf[g.id] ?? [])];
    while (stack.length > 0) {
      const cid = stack.pop()!;
      const cg = groupById.get(cid);
      if (!cg) continue;
      for (const sid of (cg.node_ids ?? cg.nodeIds ?? [])) {
        if (stepPositions[sid]) transitiveStepIds.add(sid);
      }
      stack.push(...(childGroupsOf[cid] ?? []));
    }

    const childFreshness = [...transitiveStepIds]
      .map((id) => nodeFreshness?.[id])
      .filter((f): f is NodeFreshness => f != null);
    const worstFromChildren: NodeFreshness | undefined =
      childFreshness.find((f) => f === "stale")
      ?? childFreshness.find((f) => f === "due")
      ?? childFreshness.find((f) => f === "never")
      ?? (childFreshness.length > 0 ? "fresh" : undefined);
    const ownFreshness = groupFreshness?.[g.id];
    const worstFreshness: NodeFreshness | undefined = ownFreshness ?? worstFromChildren;

    const childRunStates = [...transitiveStepIds]
      .map((id) => nodeMetrics?.[id]?.status)
      .filter((s): s is NodeRunMetrics["status"] => s != null);
    const worstRunState =
      childRunStates.find((s) => s === "failed")
      ?? childRunStates.find((s) => s === "stale")
      ?? childRunStates.find((s) => s === "running")
      ?? (childRunStates.length > 0 ? "success" : undefined);

    // Outer groups sit further behind (more negative zIndex) so nested
    // children layer cleanly on top.
    const depth = groupDepth[g.id] ?? 0;
    const zIndex = -1 - depth;

    nodes.push({
      id: g.id,
      type: "group",
      position: { x: bbox.x, y: bbox.y },
      data: {
        kind: "group",
        label: g.label,
        childCount: transitiveStepIds.size,
        collapsed: !!g.ui?.collapsed,
        worstFreshness,
        worstRunState,
        onGroupClick,
      },
      style: {
        width: bbox.w,
        height: bbox.h,
        zIndex,
      },
      draggable: false,
      selectable: false,
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

    const metrics = nodeMetrics?.[n.id];
    nodes.push({
      id: n.id,
      type: "step",
      position: pos,
      // Initial dimensions so the MiniMap has something to draw before
      // the ResizeObserver measures the actual DOM rect. xyflow only
      // propagates `measured.{width,height}` into MiniMap visibility
      // checks via the user-provided fields — without these, the mini-
      // map silently skips every step node on first paint.
      initialWidth: 220,
      initialHeight: 56,
      data: {
        kind: "step",
        label: ui.label ?? m?.label ?? n.step,
        category: m?.category ?? "custom",
        step: n.step,
        inputPorts,
        outputPorts,
        runState: metrics?.status,
        rowsOut: metrics?.rows_out ?? null,
        finishedAtMs: metrics?.finished_at_ms ?? null,
        freshness: nodeFreshness?.[n.id],
      },
      style: dimNode(n.id),
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
      initialWidth: 180,
      initialHeight: 50,
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

  return { rfNodes: nodes, rfEdges: edges, groupBboxes };
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

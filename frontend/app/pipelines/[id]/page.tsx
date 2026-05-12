"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  api,
  API_BASE,
  type Dataset,
  type PipelineDocument,
  type PipelineNode,
  type RunOut,
  type RunOutputPage,
  type StepManifest,
} from "@/lib/api/client";
import { subscribe } from "@/lib/api/ws";
import { previewPipeline, type PreviewResult } from "@/lib/engine/dispatcher";
import { humanizeSqlError } from "@/lib/humanize-sql-error";
import { SuggestFix } from "@/components/canvas/suggest-fix";
import { StepImageOrFallback } from "@/components/canvas/step-image-preview";
import { ChartDensityWarning } from "@/components/canvas/chart-density-warning";
import { usePersistedState } from "@/lib/use-persisted-state";
import { recordAction } from "@/lib/settings";
import { Tour, type TourStep } from "@/components/tour/tour";
import { Button, buttonVariants } from "@/components/ui/button";
import { LiveGrid } from "@/components/grid/live-grid";
import { GraphCanvas } from "@/components/canvas/graph-canvas";
import {
  GroupActionBar,
  GroupEditPopover,
} from "@/components/canvas/group-actions";
import { SankeyView } from "@/components/canvas/sankey-view";
import { ColumnDNAView } from "@/components/canvas/column-dna-view";
import { PipelineStrip } from "@/components/canvas/pipeline-strip";
import { QuickAddMenu } from "@/components/canvas/quick-add-menu";
import { ExportMenu } from "@/components/canvas/export-menu";
import { CompareButton } from "@/components/canvas/compare-button";
import { ReviewPanel } from "@/components/canvas/review-panel";
import { ShareDialog } from "@/components/canvas/share-dialog";
import { LineagePanel } from "@/components/lineage-panel";
import { SqlView } from "@/components/canvas/sql-view";
import { useExpertise } from "@/lib/settings";
import { ExplainPipelineButton } from "@/components/canvas/explain-pipeline";
import { SuggestNextButton } from "@/components/canvas/suggest-next";
import { LineageDrawer } from "@/components/canvas/lineage-drawer";
import { ParamForm } from "@/components/canvas/param-form";
import { SaveIndicator } from "@/components/canvas/save-indicator";
import { SuggestionsPanel } from "@/components/canvas/suggestions-panel";
import { AiVizHints } from "@/components/canvas/ai-viz-hints";
import { ExplainDataset } from "@/components/canvas/explain-dataset";
import { AiSuggestSteps } from "@/components/canvas/ai-suggest-steps";
import { SamplingDialog } from "@/components/canvas/sampling-dialog";
import { LabelPromptDialog } from "@/components/canvas/label-prompt-dialog";
import { PublishAsStepDialog, type PublishedAsStepConfig } from "@/components/canvas/publish-as-step-dialog";
import { SubPipelinePinBadge } from "@/components/canvas/sub-pipeline-pin-badge";
import { PipelineTags } from "@/components/pipeline-tags";
import { PositiveLoader } from "@/components/positive-loader";
import {
  PipelineDoctorDialog,
  filterDismissed,
  recordDismissals,
} from "@/components/canvas/pipeline-doctor-dialog";
import { diagnose, applyFixes, type Diagnosis } from "@/lib/pipeline-doctor";
import type { SamplingConfig } from "@/lib/sampling";
import { DiffStrip, diffColumns, type DiffSummary } from "@/components/canvas/diff-strip";
import { RunHistory } from "@/components/canvas/run-history";
import { HelpLink } from "@/components/help-link";
import { ArtifactsPanel } from "@/components/canvas/artifacts-panel";
import type { ColumnAction } from "@/components/canvas/column-menu";
import { suggestionsFromProfile, type Suggestion } from "@/lib/suggestions";
import { fmtInt } from "@/lib/format-number";

type PageProps = { params: Promise<{ id: string }> };

export default function PipelineEditorPage({ params }: PageProps) {
  const { id } = use(params);
  return <Editor pipelineId={id} />;
}

// ----- helpers -----

function quoteIdent(s: string): string {
  return '"' + s.replace(/"/g, '""') + '"';
}
function sqlLiteral(v: unknown): string {
  if (v === null || v === undefined) return "NULL";
  if (typeof v === "number") return String(v);
  if (typeof v === "boolean") return v ? "true" : "false";
  return "'" + String(v).replace(/'/g, "''") + "'";
}
function newNodeId(): string {
  // Prefer crypto.randomUUID() — collision-resistant. Fall back to the old
  // shape only on truly ancient browsers (FF<95, Safari<15.4, IE).
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `n_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }
  return `n_${Date.now().toString(36)}${Math.floor(Math.random() * 0xffff).toString(36)}`;
}

/** Insert a linear single-input step into a doc.
 *
 * If `afterNodeId` names an existing node or dataset, the new step is
 * spliced in IMMEDIATELY AFTER that point — its input becomes
 * afterNodeId's output, and any node that was previously consuming
 * afterNodeId's output gets re-wired to consume the new step's output.
 * The new node's array position lands right after afterNodeId so the
 * pipeline strip's linear order matches the DAG order.
 *
 * If `afterNodeId` is null/undefined, the step is appended to the end
 * of the chain (legacy behaviour).
 *
 * Why this matters: focus-aware insertion means changes go where the
 * user is looking, not at the end of the chain. Combined with per-node
 * red-status marking from /pipelines/{id}/validate, this lets the user
 * edit anywhere mid-pipeline and immediately see what downstream steps
 * (if any) were broken by the change.
 */
function insertStepAfter(
  doc: PipelineDocument,
  manifest: StepManifest,
  params: Record<string, unknown>,
  afterNodeId: string | null | undefined,
): { doc: PipelineDocument; nodeId: string } {
  const portsIn = manifest.io.inputs.ports ?? ["in"];
  const portsOut = manifest.io.outputs.ports ?? ["out"];
  const newId = newNodeId();

  // Resolve the upstream reference.
  const referenced = afterNodeId ?? doc.nodes[doc.nodes.length - 1]?.id ?? doc.datasets[0]?.id;
  if (!referenced) {
    throw new Error("Add a dataset before adding steps.");
  }
  // If `referenced` is a node, use its first output port; if a dataset, no port.
  const upstreamNode = doc.nodes.find((n) => n.id === referenced);
  const upstreamRef = upstreamNode
    ? { ref: upstreamNode.id, port: upstreamNode.outputs[0] ?? "out" }
    : { ref: referenced };

  const newNode: PipelineNode = {
    id: newId,
    step: manifest.id,
    stepVersion: manifest.version,
    inputs: { [portsIn[0]]: upstreamRef },
    outputs: portsOut,
    params,
    ui: {
      // Layout: place visually just after the upstream node when we have its
      // coordinates, else fall back to end-of-chain positioning.
      x: upstreamNode?.ui?.x != null ? upstreamNode.ui.x + 220 : 220 + doc.nodes.length * 220,
      y: upstreamNode?.ui?.y ?? 100,
      label: manifest.label,
    },
  };

  // Re-wire any node that was consuming the upstream output to consume the
  // new node's output. Without this, the new step would dangle off the side
  // of the DAG instead of being inline. We pick the first output port of
  // the new node as the new reference target.
  const newPort = portsOut[0];
  const rewired = doc.nodes.map((n) => {
    if (n.id === newId) return n;  // shouldn't happen but be safe
    let inputsChanged = false;
    const newInputs: Record<string, { ref: string; port?: string }> = {};
    for (const [port, ref] of Object.entries(n.inputs)) {
      // Match by node id; preserve port references for multi-output upstreams.
      if (ref.ref === referenced && (!upstreamNode || ref.port === upstreamNode.outputs[0])) {
        newInputs[port] = { ref: newId, port: newPort };
        inputsChanged = true;
      } else {
        newInputs[port] = ref;
      }
    }
    return inputsChanged ? { ...n, inputs: newInputs } : n;
  });

  // Insert the new node into the array right after the upstream node so
  // the linear strip order matches DAG order. Datasets aren't in the
  // nodes array, so when the upstream is a dataset we just prepend.
  let inserted: PipelineNode[];
  if (upstreamNode) {
    const idx = rewired.findIndex((n) => n.id === referenced);
    inserted = [...rewired.slice(0, idx + 1), newNode, ...rewired.slice(idx + 1)];
  } else {
    inserted = [newNode, ...rewired];
  }

  return { doc: { ...doc, nodes: inserted }, nodeId: newId };
}

// Backwards-compat alias for any caller that still uses the old name.
const appendLinearStep = (
  doc: PipelineDocument,
  manifest: StepManifest,
  params: Record<string, unknown>,
) => insertStepAfter(doc, manifest, params, null);

/**
 * Sibling of `insertStepAfter` that branches off `afterNodeId` instead
 * of inserting into the chain. The new node consumes `afterNodeId`'s
 * output, but **existing successors of `afterNodeId` are NOT re-wired**
 * — they keep their original input. Result: the original chain
 * continues unchanged, the new node hangs off as a parallel branch.
 *
 * Used when the user applies an AI route while focused on a step that
 * already has downstream successors. Inserting linearly there would
 * silently rewire those successors through the new step (likely
 * unintended); branching keeps the original flow intact.
 *
 * Layout: the branch starts vertically below the original node so it's
 * visually distinct in the canvas / strip.
 */
function branchStepAfter(
  doc: PipelineDocument,
  manifest: StepManifest,
  params: Record<string, unknown>,
  afterNodeId: string,
): { doc: PipelineDocument; nodeId: string } {
  const portsIn = manifest.io.inputs.ports ?? ["in"];
  const portsOut = manifest.io.outputs.ports ?? ["out"];
  const newId = newNodeId();

  const upstreamNode = doc.nodes.find((n) => n.id === afterNodeId);
  const upstreamRef = upstreamNode
    ? { ref: upstreamNode.id, port: upstreamNode.outputs[0] ?? "out" }
    : { ref: afterNodeId };

  const newNode: PipelineNode = {
    id: newId,
    step: manifest.id,
    stepVersion: manifest.version,
    inputs: { [portsIn[0]]: upstreamRef },
    outputs: portsOut,
    params,
    ui: {
      // Position visually as a branch — same X as upstream, offset Y.
      x: upstreamNode?.ui?.x ?? 220 + doc.nodes.length * 220,
      y: (upstreamNode?.ui?.y ?? 100) + 140,
      label: manifest.label,
    },
  };

  // KEY DIFFERENCE FROM insertStepAfter: do NOT re-wire successors.
  // Append the new node at the end of the array (so the strip shows
  // the branch after its parent's chain).
  return {
    doc: { ...doc, nodes: [...doc.nodes, newNode] },
    nodeId: newId,
  };
}

/** Returns true when `nodeId` has at least one downstream successor. */
function hasSuccessors(doc: PipelineDocument, nodeId: string): boolean {
  for (const n of doc.nodes) {
    if (n.id === nodeId) continue;
    for (const ref of Object.values(n.inputs)) {
      if (ref.ref === nodeId) return true;
    }
  }
  return false;
}

/** Set of all transitive descendants of `nodeId` (downstream successors,
 *  recursively). Used to filter eligible upstream sources for a join's
 *  input — wiring a join to its own descendant would create a cycle. */
function descendantsOf(doc: PipelineDocument, nodeId: string): Set<string> {
  const out = new Set<string>();
  const queue = [nodeId];
  while (queue.length) {
    const cur = queue.shift()!;
    for (const n of doc.nodes) {
      if (n.id === cur) continue;
      for (const ref of Object.values(n.inputs)) {
        if (ref.ref === cur && !out.has(n.id)) {
          out.add(n.id);
          queue.push(n.id);
        }
      }
    }
  }
  return out;
}

/** Eligible upstream sources for a join's left/right port: every dataset
 *  + every node that isn't the join itself or a descendant of it. */
export interface EligibleSource {
  id: string;
  kind: "dataset" | "node";
  label: string;
}
function eligibleSourcesFor(
  doc: PipelineDocument,
  joinNodeId: string,
  datasetLabelByRefId: Record<string, string> = {},
): EligibleSource[] {
  const dead = descendantsOf(doc, joinNodeId);
  dead.add(joinNodeId);
  const out: EligibleSource[] = [];
  for (const d of doc.datasets) {
    // `d.name` isn't on the strict PipelineDataset type (the schema only
    // requires `id`/`connector`/`uri`); the demo / older saved pipelines
    // do still include it in `extra`. Read defensively via a typed cast.
    const dn = (d as { name?: string }).name;
    out.push({
      id: d.id,
      kind: "dataset",
      label: datasetLabelByRefId[d.id] ?? dn ?? d.id,
    });
  }
  for (const n of doc.nodes) {
    if (dead.has(n.id)) continue;
    out.push({
      id: n.id,
      kind: "node",
      label: (n.ui as { label?: string } | undefined)?.label ?? n.step,
    });
  }
  return out;
}

/** Pick a unique branch suffix for a join we're cloning — `· branch 2`,
 *  `· branch 3`, … so two rapid rewires don't collide on label. */
function nextBranchLabel(doc: PipelineDocument, baseLabel: string): string {
  const existing = doc.nodes
    .map((n) => (n.ui as { label?: string } | undefined)?.label ?? "")
    .filter((l) => l.startsWith(baseLabel));
  // Look for ` · branch N` in existing labels; pick highest N + 1.
  let max = 1;
  for (const lbl of existing) {
    const m = lbl.match(/· branch (\d+)$/);
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return `${baseLabel} · branch ${max + 1}`;
}

/**
 * Rewire one port on a node. Terminal nodes (no successors) mutate
 * inline; mid-chain nodes branch a clone with the new wiring so the
 * existing downstream chain is preserved unchanged.
 *
 * Caller is expected to setFocusedId() to `nodeId` of the result so
 * the panel follows the branch.
 */
function rewireOrBranchInput(
  doc: PipelineDocument,
  joinNodeId: string,
  port: string,
  newRef: string,
): { doc: PipelineDocument; nodeId: string; branched: boolean } {
  const join = doc.nodes.find((n) => n.id === joinNodeId);
  if (!join) return { doc, nodeId: joinNodeId, branched: false };
  if (join.inputs[port]?.ref === newRef) {
    return { doc, nodeId: joinNodeId, branched: false };
  }
  const referenced = doc.nodes.find((n) => n.id === newRef);
  const newPortRef = referenced
    ? { ref: referenced.id, port: referenced.outputs[0] ?? "out" }
    : { ref: newRef };

  if (!hasSuccessors(doc, joinNodeId)) {
    const nextNodes = doc.nodes.map((n) =>
      n.id === joinNodeId
        ? { ...n, inputs: { ...n.inputs, [port]: newPortRef } }
        : n,
    );
    return { doc: { ...doc, nodes: nextNodes }, nodeId: joinNodeId, branched: false };
  }

  const baseLabel = (join.ui as { label?: string } | undefined)?.label ?? join.step;
  const newId = newNodeId();
  const clone: PipelineNode = {
    ...join,
    id: newId,
    inputs: { ...join.inputs, [port]: newPortRef },
    ui: {
      ...join.ui,
      x: ((join.ui as { x?: number } | undefined)?.x ?? 0) + 80,
      y: ((join.ui as { y?: number } | undefined)?.y ?? 0) + 140,
      label: nextBranchLabel(doc, baseLabel.replace(/\s*· branch \d+$/, "")),
    },
  };
  return {
    doc: { ...doc, nodes: [...doc.nodes, clone] },
    nodeId: newId,
    branched: true,
  };
}

/**
 * Flip a join's left/right inputs (and the params that name them).
 *
 * What gets swapped:
 *   - inputs.left ↔ inputs.right
 *   - keys[].left ↔ keys[].right
 *   - kind: left ↔ right, anti_left ↔ anti_right (inner / full unchanged)
 *   - suffixes[0] ↔ suffixes[1]
 *   - outputColumns provenance: L:<x> ↔ R:<x>
 *
 * Terminal joins mutate inline; mid-chain joins branch a clone.
 */
function swapJoinSides(
  doc: PipelineDocument,
  joinNodeId: string,
): { doc: PipelineDocument; nodeId: string; branched: boolean } {
  const join = doc.nodes.find((n) => n.id === joinNodeId);
  if (!join) return { doc, nodeId: joinNodeId, branched: false };
  const left = join.inputs.left;
  const right = join.inputs.right;
  if (!left || !right) return { doc, nodeId: joinNodeId, branched: false };

  const swappedInputs = { ...join.inputs, left: right, right: left };

  const params = (join.params ?? {}) as Record<string, unknown>;
  const swappedParams: Record<string, unknown> = { ...params };
  if (Array.isArray(params.keys)) {
    swappedParams.keys = (
      params.keys as Array<{ left: string; right: string; op?: string }>
    ).map((k) => ({ left: k.right, right: k.left, op: k.op }));
  }
  const kind = (params.kind ?? params.how) as string | undefined;
  if (kind === "left") swappedParams.kind = "right";
  else if (kind === "right") swappedParams.kind = "left";
  else if (kind === "anti_left") swappedParams.kind = "anti_right";
  else if (kind === "anti_right") swappedParams.kind = "anti_left";
  swappedParams.how = undefined;
  if (Array.isArray(params.suffixes) && (params.suffixes as string[]).length >= 2) {
    const sx = params.suffixes as string[];
    swappedParams.suffixes = [sx[1], sx[0]];
  }
  if (params.outputColumns && typeof params.outputColumns === "object") {
    const oc = params.outputColumns as { excluded?: string[]; renames?: Record<string, string> };
    const flip = (s: string) =>
      s.startsWith("L:") ? "R:" + s.slice(2) : s.startsWith("R:") ? "L:" + s.slice(2) : s;
    swappedParams.outputColumns = {
      excluded: (oc.excluded ?? []).map(flip),
      renames: Object.fromEntries(
        Object.entries(oc.renames ?? {}).map(([k, v]) => [flip(k), v]),
      ),
    };
  }

  if (!hasSuccessors(doc, joinNodeId)) {
    const nextNodes = doc.nodes.map((n) =>
      n.id === joinNodeId ? { ...n, inputs: swappedInputs, params: swappedParams } : n,
    );
    return { doc: { ...doc, nodes: nextNodes }, nodeId: joinNodeId, branched: false };
  }

  const baseLabel = (join.ui as { label?: string } | undefined)?.label ?? join.step;
  const newId = newNodeId();
  const clone: PipelineNode = {
    ...join,
    id: newId,
    inputs: swappedInputs,
    params: swappedParams,
    ui: {
      ...join.ui,
      x: ((join.ui as { x?: number } | undefined)?.x ?? 0) + 80,
      y: ((join.ui as { y?: number } | undefined)?.y ?? 0) + 140,
      label: nextBranchLabel(doc, baseLabel.replace(/\s*· branch \d+$/, "")),
    },
  };
  return {
    doc: { ...doc, nodes: [...doc.nodes, clone] },
    nodeId: newId,
    branched: true,
  };
}

/**
 * Whether a step's primary output is best previewed as an image
 * artifact rather than tabular rows. Used by the live-preview path
 * to mount `StepImageOrFallback` directly instead of attempting a
 * SQL/Polars row preview that would either fail or render the
 * underlying frame instead of the chart.
 *
 * Manifest-driven so new viz / chart steps light up automatically:
 *   - any `category=visualize` step whose browser engine isn't `sql`
 *     produces an image (export_to_image, funnel_chart, pareto_chart,
 *     waterfall_chart, …)
 *   - plus the model-category steps that emit a chart preview as
 *     their primary user-facing output (forecast, seasonal_decompose)
 *
 * Returning false from here doesn't break the step — it just routes
 * its preview through the row path. Returning true on a step that
 * actually produces rows would silently hide them, so the heuristic
 * is conservative.
 */
function isChartFirstStep(manifest: StepManifest | undefined): boolean {
  if (!manifest) return false;
  // Any visualize-category step that can't run in browser SQL is
  // necessarily an image-rendering step (the only other browser
  // engine values are "polars" which doesn't run client-side, or
  // "none"). The new viz pack (funnel_chart, pareto_chart,
  // waterfall_chart) lands here automatically.
  if (manifest.category === "visualize" && manifest.engine?.browser !== "sql") {
    return true;
  }
  // Model-category exceptions — these produce a chart preview as
  // their headline output even though the manifest category is "model".
  return manifest.id === "forecast" || manifest.id === "seasonal_decompose";
}

function removeNodeFromDoc(doc: PipelineDocument, nodeId: string): PipelineDocument {
  return {
    ...doc,
    datasets: doc.datasets.filter((d) => d.id !== nodeId),
    nodes: doc.nodes
      .filter((n) => n.id !== nodeId)
      .map((n) => ({
        ...n,
        inputs: Object.fromEntries(
          Object.entries(n.inputs).filter(([_, ref]) => ref.ref !== nodeId),
        ),
      })),
    outputs: doc.outputs.filter((o) => o.from.ref !== nodeId && o.id !== nodeId),
  };
}

function setNodeParams(doc: PipelineDocument, nodeId: string, params: Record<string, unknown>): PipelineDocument {
  return {
    ...doc,
    nodes: doc.nodes.map((n) => (n.id === nodeId ? { ...n, params } : n)),
  };
}

/** Toggle exposure of a single node param. Used by the param-form's
 *  🪆 expose pill. When `next` is null, removes the entry; otherwise
 *  upserts it. Cleans up an empty exposedParams object so the doc
 *  doesn't accumulate dead keys. */
function setNodeExposedParam(
  doc: PipelineDocument,
  nodeId: string,
  paramKey: string,
  next: { alias: string; help?: string } | null,
): PipelineDocument {
  return {
    ...doc,
    nodes: doc.nodes.map((n) => {
      if (n.id !== nodeId) return n;
      const ui = (n.ui ?? {}) as { exposedParams?: Record<string, { alias: string; help?: string }> };
      const exposed = { ...(ui.exposedParams ?? {}) };
      if (next === null) delete exposed[paramKey];
      else exposed[paramKey] = next;
      const nextUi: typeof ui = { ...ui };
      if (Object.keys(exposed).length === 0) delete nextUi.exposedParams;
      else nextUi.exposedParams = exposed;
      return { ...n, ui: nextUi as typeof n.ui };
    }),
  };
}

function emptyDoc(id: string, name: string): PipelineDocument {
  return { schemaVersion: 1, id, name, datasets: [], nodes: [], outputs: [] };
}

function datasetRefId(d: Dataset): string {
  return `ds_${d.id.toLowerCase()}`;
}

// ----- main editor component -----

function Editor({ pipelineId }: { pipelineId: string }) {
  const queryClient = useQueryClient();
  const pipeline = useQuery({
    queryKey: ["pipeline", pipelineId],
    queryFn: () => api.getPipeline(pipelineId),
  });
  const stepsQ = useQuery({ queryKey: ["steps"], queryFn: api.listSteps, staleTime: 60_000 });
  const datasetsQ = useQuery({ queryKey: ["datasets"], queryFn: api.listDatasets });

  // Local doc state
  const [doc, setDoc] = useState<PipelineDocument | null>(null);
  const [etag, setEtag] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  // Persist focused step + tab per pipeline so re-opening a 30-step pipeline
  // returns to where you were instead of resetting to the last node.
  const [focusedId, setFocusedId] = usePersistedState<string | null>(
    `dig.editor.focused.${pipelineId}`, null,
  );
  const [schemas, setSchemas] = useState<Record<string, Record<string, string>>>({});
  // Per-node compile status from /pipelines/{id}/validate. Drives the
  // PipelineStrip's red-pill rendering. Empty until the first validate
  // completes; older backends that don't emit `nodeStatus` leave it empty
  // and the strip stays in its non-status mode.
  const [nodeStatus, setNodeStatus] = useState<Record<string, { ok: boolean; error?: string }>>({});

  // Tour-of-pipeline
  const undoStack = useRef<PipelineDocument[]>([]);
  const redoStack = useRef<PipelineDocument[]>([]);
  const lastSnapshot = useRef<string>("");
  // Mirror stack lengths into state so the toolbar Undo/Redo buttons can
  // re-render their `disabled` attribute. Reading from refs alone made the
  // buttons stay greyed out until some unrelated state change triggered a
  // render.
  const [undoLen, setUndoLen] = useState(0);
  const [redoLen, setRedoLen] = useState(0);

  // Right panel tab
  // Default to params: a focused-step user almost always wants to edit it,
  // not stare at hints. Persisted per-pipeline so reopens land where you left.
  const [tab, setTab] = usePersistedState<"params" | "hints" | "lineage">(
    `dig.editor.tab.${pipelineId}`, "params",
  );

  // 🛤 Strip / 🕸 Graph view mode for the bottom canvas — persisted globally
  // (not per-pipeline) since this is a personal viewing preference.
  const [canvasView, setCanvasView] = usePersistedState<"strip" | "graph">(
    "dig.editor.canvasView", "strip",
  );

  // Bottom-region height when in graph view. Strip has a deterministic
  // height (~38px) so we hard-code it; the graph is freely resizable
  // because the user wants to see more or less of their pipeline DAG
  // depending on its complexity. Persisted globally (not per-pipeline).
  const [graphHeight, setGraphHeight] = usePersistedState<number>(
    "dig.editor.graphHeight", 300,
  );

  // 🧪 Sampling popup. Per-pipeline so two flows can use different
  // strategies (head for stable canaries; random for representative
  // EDA). The persisted config lives on doc.metadata.sampling.
  const [samplingOpen, setSamplingOpen] = useState(false);

  // Per-session set of chart node ids whose density warning the user
  // has explicitly dismissed. Banner stays hidden until reload OR
  // the chart's input row count drops back under threshold (then
  // reappears next time it's exceeded). Not persisted — same idea
  // as the row-cap badge: warning fatigue should expire with the tab.
  const [dismissedDensityWarnings, setDismissedDensityWarnings] = useState<
    Set<string>
  >(() => new Set());

  // 🪆 Publish-as-step dialog state. The doc.metadata.publishedAsStep
  // entry promotes this pipeline into the global step picker.
  const [publishOpen, setPublishOpen] = useState(false);

  // 🩺 Pipeline doctor — runs structural checks on load and surfaces a
  // friendly "tune-up" dialog when fixable issues are found. State:
  //   `pendingDiagnoses` non-empty → dialog open
  //   `doctorRanFor`  ref guards against re-firing on every doc edit
  //                    (only run once per (pipelineId, etag)).
  const [pendingDiagnoses, setPendingDiagnoses] = useState<Diagnosis[]>([]);
  const doctorRanFor = useRef<string | null>(null);

  // Editor tour open state. Manually triggered via the 🧭 toolbar button —
  // auto-firing was removed because the tour overlay swallowed clicks on
  // the Add-dataset dropdown.
  const [editorTourOpen, setEditorTourOpen] = useState(false);
  const [lineagePanel, setLineagePanel] = useState<{ nodeId: string; column: string } | null>(null);
  // Phase A Layer 7 — Column DNA full-screen view.
  const [columnDNA, setColumnDNA] = useState<{ nodeId: string; column: string } | null>(null);
  const [sqlViewOpen, setSqlViewOpen] = useState(false);
  const expertise = useExpertise();

  // Track whether we've already seeded state for this pipeline. Without this,
  // every WS-triggered refetch (which mints a new `pipeline.data` reference)
  // re-runs the seed and clobbers the user's current focus + clears undo /
  // redo mid-edit. Seed once per pipelineId; thereafter let updates flow
  // through the event handlers, not this effect.
  const seededFor = useRef<string | null>(null);
  useEffect(() => {
    if (pipeline.data && seededFor.current !== pipelineId) {
      // Deep-clone the seed so our React state doesn't share object
      // references with React Query's cache. Defensive: prevents any
      // future code that mutates `pipeline.data.document` (or
      // structural-sharing on a subsequent refetch) from silently
      // updating our React state out from under us. Cheap
      // (~1ms for typical doc sizes).
      const seed =
        Object.keys(pipeline.data.document).length === 0
          ? emptyDoc(pipelineId, "Untitled")
          : (JSON.parse(JSON.stringify(pipeline.data.document)) as PipelineDocument);
      setDoc(seed);
      setEtag(pipeline.data.etag);
      setDirty(false);
      undoStack.current = [];
      redoStack.current = [];
      setUndoLen(0);
      setRedoLen(0);
      lastSnapshot.current = JSON.stringify(seed);
      // Default focus = last node, else the dataset
      const lastNode = seed.nodes[seed.nodes.length - 1];
      setFocusedId(lastNode?.id ?? seed.datasets[0]?.id ?? null);
      seededFor.current = pipelineId;
    } else if (pipeline.data && seededFor.current === pipelineId) {
      // Subsequent refetches: keep doc/focus state, just refresh etag so
      // optimistic mutations align with the server's view.
      setEtag(pipeline.data.etag);
    }
  }, [pipeline.data, pipelineId]);

  // Subscribe to multi-session pipeline events.
  //
  // Using refs for etag + dirty so the effect deps stay stable — previously
  // we depended on both, which caused the WS to tear down and reconnect on
  // every save (~50ms blip during which any backend event was lost).
  //
  // On reconnect (after a backend restart or laptop wake), force-invalidate
  // the pipeline query — without this, a save made by another session while
  // the socket was down would never reach us, and our next save would 409
  // with no actionable error. The runtime audit caught this exact path.
  const etagRef = useRef(etag);
  const dirtyRef = useRef(dirty);
  useEffect(() => { etagRef.current = etag; }, [etag]);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  useEffect(() => {
    const teardown = subscribe(
      `/ws/pipelines/${pipelineId}`,
      (msg) => {
        const p = msg.payload as { event?: string; etag?: number };
        if (p.event === "changed" && typeof p.etag === "number" && p.etag !== etagRef.current) {
          if (dirtyRef.current) {
            toast.warning(`Another session saved (v${p.etag}). Reload to see it.`, { duration: 8000 });
          } else {
            queryClient.invalidateQueries({ queryKey: ["pipeline", pipelineId] });
            toast.info(`📡 Synced from another session (v${p.etag})`);
          }
        }
      },
      {
        onOpen: (isFirst) => {
          if (isFirst) return;  // initial connect already loads via the query
          // Reconnect: another session may have advanced etag while we were
          // disconnected. Refetch + warn the user if they have unsaved edits.
          queryClient.invalidateQueries({ queryKey: ["pipeline", pipelineId] });
          if (dirtyRef.current) {
            toast.warning(
              "🔌 Reconnected. Your local edits are preserved; the backend may have a newer version — verify before saving.",
              { duration: 10_000 },
            );
          } else {
            toast.success("🔌 Reconnected", { duration: 2000 });
          }
        },
      },
    );
    return teardown;
  }, [pipelineId, queryClient]);

  // ---- Undo / redo wrapper ----
  const updateDoc = useCallback((next: PipelineDocument) => {
    setDoc((prev) => {
      if (prev) {
        const snap = JSON.stringify(prev);
        if (snap !== lastSnapshot.current) {
          undoStack.current.push(prev);
          if (undoStack.current.length > 80) undoStack.current.shift();
          redoStack.current = [];
          lastSnapshot.current = snap;
          setUndoLen(undoStack.current.length);
          setRedoLen(0);
        }
      }
      return next;
    });
    setDirty(true);
  }, []);

  const undo = useCallback(() => {
    if (undoStack.current.length === 0) return;
    setDoc((cur) => {
      if (!cur) return cur;
      const prev = undoStack.current.pop()!;
      redoStack.current.push(cur);
      lastSnapshot.current = JSON.stringify(prev);
      setDirty(true);
      setUndoLen(undoStack.current.length);
      setRedoLen(redoStack.current.length);
      return prev;
    });
  }, []);
  const redo = useCallback(() => {
    if (redoStack.current.length === 0) return;
    setDoc((cur) => {
      if (!cur) return cur;
      const next = redoStack.current.pop()!;
      undoStack.current.push(cur);
      lastSnapshot.current = JSON.stringify(next);
      setDirty(true);
      setUndoLen(undoStack.current.length);
      setRedoLen(redoStack.current.length);
      return next;
    });
  }, []);

  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      const cmd = e.metaKey || e.ctrlKey;
      const target = e.target as HTMLElement | null;
      const isInput = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (cmd && e.key.toLowerCase() === "z" && !e.shiftKey && !isInput) {
        e.preventDefault();
        undo();
      } else if (cmd && ((e.key.toLowerCase() === "z" && e.shiftKey) || e.key.toLowerCase() === "y") && !isInput) {
        e.preventDefault();
        redo();
      } else if (cmd && e.key.toLowerCase() === "s" && !e.shiftKey) {
        // ⌘S — open the labeled-checkpoint dialog. Always preventDefault
        // so the browser doesn't try to download the page even when an
        // input is focused (autosave already preserved the text).
        e.preventDefault();
        setSaveDialogOpen(true);
      } else if (cmd && e.key.toLowerCase() === "s" && e.shiftKey) {
        // ⌘⇧S — Save As (clone). Same convention as most editors.
        e.preventDefault();
        setSaveAsDialogOpen(true);
      }
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [undo, redo]);

  // ---- Save (debounced auto-save + explicit "Save" button) ----
  //
  // Two distinct save flavors:
  //   - autosave  : keystroke-driven, transient. Server keeps only the
  //                 last 5; useful for crash recovery + multi-tab sync.
  //   - manual_save: user pressed the Save button (with optional label).
  //                  Server keeps up to 50; survives history pruning.
  //
  // Both bump etag (so the WS sync still works); they only differ in how
  // the snapshot is *retained* on the server.
  const lastNodeCountRef = useRef<number>(0);
  const saveMutation = useMutation({
    mutationFn: async (args: {
      next: PipelineDocument;
      triggeredBy: "manual_save" | "autosave";
      changeReason?: string | null;
    }) => {
      if (etag == null) throw new Error("etag unset");
      return api.updatePipeline(pipelineId, args.next, etag, {
        triggeredBy: args.triggeredBy,
        changeReason: args.changeReason,
      });
    },
    onSuccess: (resp, variables) => {
      setEtag(resp.etag);
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ["pipelines"] });
      // Adaptive UI: bump action counter — heavier weight for step add,
      // lighter for param edits. Auto-promotes Beginner → Builder at threshold.
      const nodeCount = variables.next.nodes?.length ?? 0;
      const weight = nodeCount > lastNodeCountRef.current ? 2 : 1;
      lastNodeCountRef.current = nodeCount;
      const promoted = recordAction(weight);
      if (promoted) {
        toast.success("🪴 You're a Builder now — full step library unlocked. ⌘⇧E to switch back.");
      }
      if (variables.triggeredBy === "manual_save") {
        toast.success(
          variables.changeReason
            ? `💾 Saved · "${variables.changeReason}"`
            : "💾 Saved",
        );
      }
    },
    onError: (e: Error) => {
      // Cycle errors are 409s with "Cycle detected" or "Self-reference".
      // Show as a long-duration toast with explicit guidance — these
      // need user intervention before any further save will succeed.
      const msg = e.message;
      const isCycle = /cycle detected|self-reference/i.test(msg);
      if (isCycle) {
        toast.error(
          `🔁 ${msg}\n\nTip: remove the offending sub-pipeline step or unpublish the source.`,
          { duration: 12000 },
        );
      } else {
        toast.error(`Save failed: ${msg}`);
      }
    },
  });
  useEffect(() => {
    if (!doc || !dirty) return;
    // Don't fire a second autosave while the previous one is still in
    // flight — the etag bump from the first save's onSuccess hasn't run
    // yet, so the second mutate would PUT with a stale etag and 409.
    // The user sees a "Save failed" toast for an autosave they didn't
    // even know happened. Re-running the effect once saveMutation
    // finishes (via dependency on isPending below) catches up.
    if (saveMutation.isPending) return;
    const t = setTimeout(
      () => saveMutation.mutate({ next: doc, triggeredBy: "autosave" }),
      500,
    );
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, dirty, saveMutation.isPending]);

  // ---- Save / Save-As dialogs (explicit checkpoint + clone) ----
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveAsDialogOpen, setSaveAsDialogOpen] = useState(false);
  const router = useRouter();
  const cloneMutation = useMutation({
    mutationFn: async (name: string) => {
      if (!doc) throw new Error("no document");
      // Make sure the latest in-memory edits are persisted before cloning;
      // otherwise the new copy starts from the server's older state.
      if (dirty && etag != null) {
        await api.updatePipeline(pipelineId, doc, etag, { triggeredBy: "autosave" });
      }
      return api.clonePipeline(pipelineId, name);
    },
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ["pipelines"] });
      // `resp.name` isn't on the openapi-generated Pipeline shape — the
      // clone endpoint pulls the name out of `document.name`. Cast for the
      // toast label only; if missing we fall back to the new id.
      const cloneName = (resp as { name?: string }).name ?? resp.id;
      toast.success(`📋 Cloned to "${cloneName}"`);
      router.push(`/pipelines/${resp.id}`);
    },
    onError: (e: Error) => toast.error(`Save As failed: ${e.message}`),
  });
  const onSaveExplicit = (label: string | null) => {
    if (!doc) return;
    saveMutation.mutate({
      next: doc,
      triggeredBy: "manual_save",
      changeReason: label || null,
    });
    setSaveDialogOpen(false);
  };
  const onSaveAs = (newName: string) => {
    cloneMutation.mutate(newName);
    setSaveAsDialogOpen(false);
  };

  // ---- Validation / schema inference (server-side) ----
  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.validatePipeline(pipelineId);
        if (cancelled) return;
        setSchemas(res.schemas ?? {});
        setNodeStatus(res.nodeStatus ?? {});
        // Surface validation errors that block downstream work (cycle in DAG,
        // unknown step id, etc.). Without this, the user sees no schemas and
        // gets no clue why. Stay silent for the common "pipeline is empty
        // / param is required" cases since those are user-WIP, not real errors.
        if (res.errors && res.errors.length > 0) {
          const meaningful = res.errors.filter(
            (e) => !/required param|missing/i.test(e),
          );
          if (meaningful.length > 0) {
            console.warn("validatePipeline:", meaningful);
            // One toast per distinct first-meaningful-error per render.
            toast.warning(
              `⚠️ Pipeline structure issue: ${meaningful[0]}`,
              { id: `validate-${pipelineId}`, duration: 6000 },
            );
          }
        }
      } catch (e) {
        // Network/server-side failure — log but don't toast (the run itself
        // would surface a more actionable error if the user actually tried).
        console.warn("validatePipeline failed:", (e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [doc, pipelineId, etag]);

  // ---- Manifests by id ----
  const manifestsById = useMemo(() => {
    const m: Record<string, StepManifest> = {};
    for (const s of stepsQ.data ?? []) m[s.id] = s;
    return m;
  }, [stepsQ.data]);

  // ---- Auto-debounced live preview tied to focused step ----
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  // Per-focus diagnostic view for joins. Default 'matched' is the
  // saved join behaviour; 'unmatched_left' / 'unmatched_right' rewrite
  // to anti-* for the focused node only (not persisted in the doc).
  const [joinViewMode, setJoinViewMode] = useState<
    "matched" | "unmatched_left" | "unmatched_right"
  >("matched");
  const previewAbort = useRef<AbortController | null>(null);
  // Holds a pending error surface — when a compile fails we don't blank the
  // grid immediately. Instead we schedule the error to appear after a short
  // window; if a successful preview lands first, the timer is cancelled and
  // the user never sees the transient error flash. This is the load-bearing
  // piece behind "no flicker on column actions."
  const errorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (errorTimer.current) {
      clearTimeout(errorTimer.current);
      errorTimer.current = null;
    }
  }, []);

  // ---- Pipeline doctor — run once per (pipelineId, etag) ----------
  // Why an etag-keyed guard: every keystroke bumps `doc` reference and
  // would otherwise re-fire the diagnose call constantly. We only want
  // to run it on initial load (the etag from the server) — once the
  // user starts editing locally, the autosave model handles
  // consistency. The `doctorRanFor` ref combines pipelineId + etag so
  // each fresh load is fresh-checked.
  useEffect(() => {
    if (!doc || !datasetsQ.data || !stepsQ.data || etag == null) return;
    const guardKey = `${pipelineId}:${etag}`;
    if (doctorRanFor.current === guardKey) return;
    doctorRanFor.current = guardKey;
    const all = diagnose(doc, datasetsQ.data, stepsQ.data);
    const undismissed = filterDismissed(pipelineId, all);
    if (undismissed.length > 0) {
      setPendingDiagnoses(undismissed);
    }
    // doc dep is intentionally missing — see the etag-guard above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetsQ.data, stepsQ.data, etag, pipelineId]);

  const isFocusedDataset = useMemo(() => {
    if (!doc || !focusedId) return false;
    return doc.datasets.some((d) => d.id === focusedId);
  }, [doc, focusedId]);

  // Fetch raw rows when focused on a dataset. Two-tier lookup:
  //   1. Strict — `ds_<ulid_lowercase>` (the canonical convention used
  //      by everything created after the convention was settled).
  //   2. URI fallback — extract the ULID from the doc's `uri` field
  //      (`.../<ULID>.parquet`) and match the Dataset row directly by id.
  //      Handles pipelines whose dataset id is a doc-internal alias
  //      (`ds_main`, `ds_orders`, …) rather than `ds_<ulid_lowercase>`.
  //      Without this fallback, those pipelines would render "No data
  //      yet — add a dataset" even though their parquet is on disk.
  const focusedDatasetReal = useMemo(() => {
    if (!doc || !focusedId || !datasetsQ.data) return null;
    const ds = doc.datasets.find((d) => d.id === focusedId);
    if (!ds) return null;
    const byConvention = datasetsQ.data.find((d) => datasetRefId(d) === focusedId);
    if (byConvention) return byConvention;
    const uriMatch = ds.uri?.match(/([0-9A-Z]{26})\.parquet/i);
    if (uriMatch) {
      const ulid = uriMatch[1].toUpperCase();
      return datasetsQ.data.find((d) => d.id.toUpperCase() === ulid) ?? null;
    }
    return null;
  }, [doc, focusedId, datasetsQ.data]);

  const datasetRowsQ = useQuery({
    queryKey: ["dataset-rows", focusedDatasetReal?.id],
    enabled: !!focusedDatasetReal,
    queryFn: () =>
      focusedDatasetReal
        ? api.getRows(focusedDatasetReal.id, 0, 200)
        : Promise.reject(new Error("no dataset")),
  });
  const datasetProfileQ = useQuery({
    queryKey: ["dataset-profile", focusedDatasetReal?.id],
    enabled: !!focusedDatasetReal,
    queryFn: () =>
      focusedDatasetReal
        ? api.getProfile(focusedDatasetReal.id)
        : Promise.reject(new Error("no dataset")),
  });

  // For node focus: run browser preview targeted at that node.
  //
  // Perceived-perf: the *first* preview fires immediately (debounce=0) so
  // landing on a node feels instant; subsequent re-renders during typing
  // debounce at 350 ms. We track the "have I rendered this focusedId yet"
  // state via a ref so re-renders triggered by upstream edits also wait.
  //
  // **Stale-while-revalidate**: the previous successful `preview` stays
  // mounted while we recompute. We only blank it when (a) focus moves to a
  // dataset / null (legitimate state change), or (b) an error has actually
  // been surfaced after the debounce window. This eliminates the flicker
  // that used to appear during column actions where a brief invalid
  // intermediate state would blank the grid → show ⚠️ → snap back.
  const previewedFocusRef = useRef<string | null>(null);
  useEffect(() => {
    if (!doc || isFocusedDataset || !focusedId) {
      setPreview(null);
      setPreviewError(null);
      if (errorTimer.current) {
        clearTimeout(errorTimer.current);
        errorTimer.current = null;
      }
      return;
    }
    if (doc.nodes.length === 0) return;
    previewAbort.current?.abort();
    // A new attempt cancels any pending error surface from the previous one
    // — if we're trying again, we shouldn't surface yesterday's failure.
    if (errorTimer.current) {
      clearTimeout(errorTimer.current);
      errorTimer.current = null;
    }
    const ac = new AbortController();
    previewAbort.current = ac;
    setPreviewLoading(true);
    // NB: we do NOT clear `preview` or `previewError` here. The grid keeps
    // rendering the last good result with a quiet "⏳ recomputing…" badge
    // (LiveGrid status strip) until either a new result lands or we decide
    // to surface a persistent error.
    const isFirstForFocus = previewedFocusRef.current !== focusedId;
    const debounceMs = isFirstForFocus ? 0 : 350;
    // Chart-first steps render via StepImagePreview directly — no need
    // to run the WASM compile path (which would just fail with a
    // "browser engine 'none'" error and waste a round trip). Skip the
    // dispatcher entirely so the user never sees an error UI flash; the
    // grid's emptyHint branch will mount StepImageOrFallback directly
    // and its internal "Rendering preview…" state is what the user sees
    // throughout the backend hop.
    const focusedNodeUpfront = focusedId
      ? doc.nodes.find((n) => n.id === focusedId)
      : null;
    if (
      focusedNodeUpfront
      && isChartFirstStep(manifestsById[focusedNodeUpfront.step])
    ) {
      // Clear any stale state from a prior step so the grid doesn't
      // briefly flash the previous preview underneath.
      if (errorTimer.current) {
        clearTimeout(errorTimer.current);
        errorTimer.current = null;
      }
      setPreviewError(null);
      setPreview(null);
      setPreviewLoading(false);
      previewedFocusRef.current = focusedId;
      return () => {
        ac.abort();
      };
    }
    const t = setTimeout(async () => {
      try {
        // Pass the focused step's id so the dispatcher knows whether
        // to fall back to backend rows (data-producing steps) or let
        // the chart-image fallback handle it (export_to_image,
        // forecast, seasonal_decompose).
        const focusedNode = focusedId
          ? doc.nodes.find((n) => n.id === focusedId)
          : null;
        const res = await previewPipeline(pipelineId, {
          terminal: focusedId,
          sampleRows: 100_000,
          previewLimit: 500,
          signal: ac.signal,
          sampling: doc.metadata?.sampling as SamplingConfig | undefined,
          terminalStepId: focusedNode?.step,
          // Only meaningful when the focused step is a join — the
          // dispatcher / backend ignore the param otherwise.
          terminalViewMode:
            focusedNode?.step === "join" ? joinViewMode : undefined,
        });
        if (!ac.signal.aborted) {
          setPreview(res);
          setPreviewError(null);
          if (errorTimer.current) {
            clearTimeout(errorTimer.current);
            errorTimer.current = null;
          }
          previewedFocusRef.current = focusedId;
        }
      } catch (e) {
        if (!ac.signal.aborted) {
          const msg = (e as Error).message;
          if (errorTimer.current) clearTimeout(errorTimer.current);
          // Hold the error in the wings — only surface if it persists past
          // the debounce window. Brief mid-mutation compile blips never
          // visibly flash. 600 ms covers a typical compile + roundtrip.
          errorTimer.current = setTimeout(() => {
            setPreviewError(msg);
            // Only NOW blank the preview — when we're actually surfacing
            // the error to the user. Up until this point the user keeps
            // seeing the last-good data with the recomputing badge.
            setPreview(null);
            errorTimer.current = null;
          }, 600);
        }
      } finally {
        if (!ac.signal.aborted) setPreviewLoading(false);
      }
    }, debounceMs);
    return () => {
      clearTimeout(t);
      ac.abort();
    };
  }, [doc, focusedId, isFocusedDataset, pipelineId, etag, joinViewMode]);

  // Reset the diagnostic view back to matched whenever the focus
  // leaves a join (or moves to a different join). The toggle is a
  // per-focus affordance; remembering it across nodes would surprise
  // the user when the next join silently shows anti-* rows.
  useEffect(() => {
    setJoinViewMode("matched");
  }, [focusedId]);

  // ---- Derived: current grid columns + rows ----
  const gridData = useMemo(() => {
    if (isFocusedDataset && focusedDatasetReal) {
      const cols =
        (datasetProfileQ.data?.columns ?? []).map((c) => ({
          name: c.name,
          // Show the logical type when the profile detector promoted the
          // column (e.g. "email", "index"). Fall back to the physical
          // polars dtype only when there's no logical interpretation.
          type: c.type ?? c.polarsType ?? "string",
          // SQL storage type from the detector pass — DECIMAL(18,4),
          // HUGEINT, UUID, … — surfaced in the header tooltip and
          // profile drawer so users can see the on-disk representation.
          storage: c.storage ?? null,
          candidates: c.candidates,
        })) ?? [];
      return {
        columns: cols,
        rows: datasetRowsQ.data?.rows ?? [],
        totalRows: focusedDatasetReal.rowCount ?? datasetRowsQ.data?.totalRows ?? 0,
        loading: datasetRowsQ.isLoading,
        elapsedMs: null as number | null,
      };
    }
    if (preview) {
      // Merge the inferred logical schema for the focused node onto the
      // preview's columns. The preview comes from DuckDB-WASM and only
      // carries physical dtypes (DOUBLE / VARCHAR / …); the logical types
      // (`currency`, `percentage`, `email`, …) live in schemas[nodeId],
      // computed by each step's infer_schema. Without this join, casting
      // a column to `currency` would still render as `num` because the
      // grid would only see DuckDB's DOUBLE.
      const nodeSchema: Record<string, string> = focusedId ? (schemas[focusedId] ?? {}) : {};
      const cols = preview.columns.map((c) => ({
        ...c,
        // Schema's logical type wins; physical dtype is the fallback.
        type: nodeSchema[c.name] ?? c.type,
      }));
      return {
        columns: cols,
        rows: preview.rows,
        totalRows: preview.rowCount,
        loading: previewLoading,
        elapsedMs: preview.elapsedMs,
      };
    }
    return { columns: [], rows: [], totalRows: 0, loading: previewLoading, elapsedMs: null };
  }, [
    isFocusedDataset,
    focusedDatasetReal,
    datasetProfileQ.data,
    datasetRowsQ.data,
    datasetRowsQ.isLoading,
    preview,
    previewLoading,
    focusedId,
    schemas,
  ]);

  // ---- Diff vs previous step ----
  const diff: DiffSummary | null = useMemo(() => {
    if (!doc || !focusedId) return null;
    const node = doc.nodes.find((n) => n.id === focusedId);
    if (!node) return null;
    // previous in topological doc-order: the most recent node before this one
    const idx = doc.nodes.findIndex((n) => n.id === focusedId);
    const prevId = idx > 0
      ? doc.nodes[idx - 1].id
      : (Object.values(node.inputs)[0]?.ref ?? null);
    if (!prevId) return null;
    const prevSchema = Object.keys(schemas[prevId] ?? {});
    const nextSchema = Object.keys(schemas[node.id] ?? {});
    if (prevSchema.length === 0 && nextSchema.length === 0) return null;
    const colDiff = diffColumns(prevSchema, nextSchema);
    const manifest = manifestsById[node.step];
    return {
      ...colDiff,
      rowDelta: null, // measured via row counts below if available
      rowsBefore: null,
      rowsAfter: null,
      stepLabel: manifest?.label ?? node.step,
    };
  }, [doc, focusedId, schemas, manifestsById]);

  // ---- Highlights for the grid ----
  const [hoveredHintColumn, setHoveredHintColumn] = useState<string | null>(null);
  const highlights = useMemo(() => {
    return {
      added: new Set(diff?.addedColumns ?? []),
      renamed: new Set((diff?.renamedColumns ?? []).map((r) => r.to)),
      hovered: hoveredHintColumn,
    };
  }, [diff?.addedColumns, diff?.renamedColumns, hoveredHintColumn]);

  // ---- Suggestions ----
  const suggestions: Suggestion[] = useMemo(() => {
    // Use the rich profile when on a dataset, else inferred from the result data (lighter).
    if (isFocusedDataset && datasetProfileQ.data) {
      return suggestionsFromProfile(
        datasetProfileQ.data.columns.map((c) => ({
          name: c.name,
          type: c.type,
          nullCount: c.nullCount,
          nullFraction: c.nullFraction,
          distinctCount: c.distinctCount,
          sampledRows: c.sampledRows,
          topValues: (c.topValues ?? []) as Array<{ value: unknown; count: number }>,
          min: c.min,
          max: c.max,
        })),
      );
    }
    // From in-memory rows of the focused step: build basic stats
    if (preview && preview.rows.length > 0) {
      const liveCols = preview.columns.map((c) => {
        const vals = preview.rows.map((r) => r[c.name]);
        const nulls = vals.filter((v) => v === null || v === undefined).length;
        const distinct = new Set(vals.map((v) => (v === null || v === undefined ? "__null__" : JSON.stringify(v)))).size;
        const counts = new Map<string, number>();
        for (const v of vals) {
          if (v === null || v === undefined) continue;
          const key = String(v);
          counts.set(key, (counts.get(key) ?? 0) + 1);
        }
        const topValues = [...counts.entries()]
          .sort((a, b) => b[1] - a[1])
          .slice(0, 5)
          .map(([value, count]) => ({ value, count }));
        return {
          name: c.name,
          type: c.type,
          nullCount: nulls,
          nullFraction: vals.length ? nulls / vals.length : 0,
          distinctCount: distinct,
          sampledRows: vals.length,
          topValues,
        };
      });
      return suggestionsFromProfile(liveCols);
    }
    return [];
  }, [isFocusedDataset, datasetProfileQ.data, preview]);

  // ---- Quick-add menu state ----
  const [quickAdd, setQuickAdd] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [stepCtx, setStepCtx] = useState<{ id: string; kind: "node" | "dataset"; x: number; y: number } | null>(null);
  const handleQuickAddClick = useCallback((e: React.MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setQuickAdd({ x: r.left, y: r.top, w: r.width, h: r.height });
  }, []);
  const onPickStep = useCallback(
    (manifest: StepManifest, paramsOverride?: Record<string, unknown>) => {
      if (!doc) return;
      // Cycle preflight: a pipeline can't include itself as a step. The
      // save-time check on the backend would catch this too, but the
      // earlier we surface it the better — silent save failures are
      // confusing. Transitive cycles still go through the backend
      // (server walks the full closure on PUT).
      if (manifest.id === `pipeline:${pipelineId}`) {
        toast.error(
          "🔁 A pipeline can't include itself as a step. Remove the publishedAsStep marker on this pipeline first, or pick a different one.",
          { duration: 7000 },
        );
        setQuickAdd(null);
        return;
      }
      try {
        // Insert after the focused step (or dataset) so changes go where
        // the user is looking, not at the end of the chain. AI ribbon
        // suggestions arrive with pre-filled params; everything else
        // falls back to the manifest's defaults.
        const params = paramsOverride
          ? { ...defaultParams(manifest), ...paramsOverride }
          : defaultParams(manifest);
        // For pipeline-composite steps the manifest declares pinnedEtag
        // = current source etag; defaultParams already picks that up
        // because it's a regular param spec.
        const { doc: next, nodeId } = insertStepAfter(doc, manifest, params, focusedId);
        updateDoc(next);
        setFocusedId(nodeId);
        setTab("params");
        toast.success(`Added ${manifest.label}`);
      } catch (e) {
        toast.error((e as Error).message);
      }
      setQuickAdd(null);
    },
    [doc, updateDoc, pipelineId],
  );

  // ---- Column actions: turn a column action into a pipeline step ----
  const currentSchema = useMemo(() => {
    if (!doc || !focusedId) return [];
    return Object.keys(schemas[focusedId] ?? {});
  }, [doc, focusedId, schemas]);

  // Phase-A-pro #5 — edit-time impact map. For the focused node, count
  // how many downstream nodes consume its output (via `inputs` refs).
  // We surface the same count for every column in the live grid: it's
  // a node-level upper bound on impact ("this column is read by N
  // downstream nodes") that the user can drill into via Column DNA.
  // Cheap O(N) over doc.nodes; no API call needed.
  const downstreamImpact = useMemo<Record<string, number> | undefined>(() => {
    if (!doc || !focusedId) return undefined;
    let count = 0;
    for (const n of doc.nodes) {
      for (const ref of Object.values(n.inputs ?? {})) {
        if (ref.ref === focusedId) {
          count++;
          break;   // count this node once even if it inputs multiple ports from the focused node
        }
      }
    }
    if (count === 0) return undefined;
    const cols = currentSchema;
    if (cols.length === 0) return undefined;
    const map: Record<string, number> = {};
    for (const c of cols) map[c] = count;
    return map;
  }, [doc, focusedId, currentSchema]);

  const handleColumnAction = useCallback(
    (a: ColumnAction) => {
      if (!doc) return;
      // Trace lineage doesn't add a step — it opens the lineage drawer
      // scoped to the focused node + clicked column.
      if (a.kind === "trace_lineage") {
        if (!focusedId) {
          toast.message("Select a step first to trace its column.");
          return;
        }
        setLineagePanel({ nodeId: focusedId, column: a.column });
        return;
      }
      if (a.kind === "column_dna") {
        if (!focusedId) {
          toast.message("Select a step first to view its column DNA.");
          return;
        }
        setColumnDNA({ nodeId: focusedId, column: a.column });
        return;
      }
      // Phase-A-pro #4 — range filter from a histogram bar click in
      // the profile drawer. Insert a `filter_rows` step downstream
      // with the BETWEEN predicate.
      if (a.kind === "range_filter") {
        const filterManifest = manifestsById["filter_rows"];
        if (!filterManifest || !focusedId) {
          toast.message("Filter step unavailable.");
          return;
        }
        const lo = Number(a.low.toPrecision(6));
        const hi = Number(a.high.toPrecision(6));
        const predicate = `"${a.column}" >= ${lo} AND "${a.column}" < ${hi}`;
        const next = insertStepAfter(doc, filterManifest, { predicate }, focusedId);
        updateDoc(next.doc);
        setFocusedId(next.nodeId);
        toast.success(`Filter ${a.column} ∈ [${lo}, ${hi}) added`);
        return;
      }
      // Composite action: pack N source columns into a struct, then cast
      // that struct to a meta-type (geographic / cartesian2d / polar2d / …).
      // Two `insertStepAfter` calls chained: the second uses the new
      // pack-step's id as `afterNodeId` so the cast lands directly downstream.
      if (a.kind === "pack_then_cast") {
        const packManifest = manifestsById["pack_struct"];
        const castManifest = manifestsById["cast_type"];
        if (!packManifest || !castManifest) {
          toast.error("Step 'pack_struct' or 'cast_type' not registered");
          return;
        }
        try {
          const prevDoc = doc;
          const { doc: afterPack, nodeId: packId } = insertStepAfter(
            doc,
            packManifest,
            { outputColumn: a.outputColumn, fields: a.fields },
            focusedId,
          );
          const { doc: afterCast, nodeId: castId } = insertStepAfter(
            afterPack,
            castManifest,
            { column: a.outputColumn, targetType: a.targetType, strict: false },
            packId,
          );
          updateDoc(afterCast);
          setFocusedId(castId);
          setTab("params");
          toast.success(`✨ Added 📦 pack_struct + 🔄 cast → ${a.targetType}`, {
            duration: 4500,
            action: { label: "Undo", onClick: () => updateDoc(prevDoc) },
          });
        } catch (e) {
          toast.error((e as Error).message);
        }
        return;
      }
      const stepId = (() => {
        switch (a.kind) {
          case "filter_eq":
          case "filter_neq":
          case "filter_isnull":
          case "filter_notnull":
            return "filter_rows";
          case "sort":
            return "sort_rows";
          case "cast":
            return "cast_type";
          case "rename":
            return "rename_columns";
          case "drop":
            return "select_columns";
          case "group_by":
            return "group_aggregate";
          case "derive_from":
            return "derive_column";
          case "reorder":
            return "reorder_columns";
          case "insert_column":
            return "add_column";
          case "visualize":
            return "export_to_image";
          case "visualize_as":
            return a.stepId;
        }
      })();
      const manifest = manifestsById[stepId];
      if (!manifest) {
        toast.error(`Step '${stepId}' not registered`);
        return;
      }
      const params = (() => {
        switch (a.kind) {
          case "filter_eq":
            return { predicate: `${quoteIdent(a.column)} = ${sqlLiteral(a.value)}` };
          case "filter_neq":
            return { predicate: `${quoteIdent(a.column)} <> ${sqlLiteral(a.value)}` };
          case "filter_isnull":
            return { predicate: `${quoteIdent(a.column)} IS NULL` };
          case "filter_notnull":
            return { predicate: `${quoteIdent(a.column)} IS NOT NULL` };
          case "sort":
            return { by: [{ column: a.column, direction: a.direction }] };
          case "cast":
            return { column: a.column, targetType: a.targetType, strict: false };
          case "rename":
            return { mapping: [{ from: a.column, to: a.to }] };
          case "drop":
            return { columns: currentSchema.filter((c) => c !== a.column) };
          case "group_by":
            return { groupBy: [a.column], aggregates: [{ fn: "count", as: "n" }] };
          case "derive_from":
            return { name: `${a.column}_derived`, expression: quoteIdent(a.column) };
          case "reorder":
            return { order: a.order };
          case "insert_column":
            // Sensible defaults — the user lands on the new step's param
            // form (setTab("params") below) and can rename / change type /
            // set a default value. The reference column + position are
            // pre-filled so the column lands exactly where they clicked.
            return {
              name: "new_column",
              columnType: "string",
              defaultValue: "",
              position: a.position,
              reference: a.reference,
            };
          case "visualize": {
            // Pick a sensible chart kind from the column's physical type:
            // numeric → histogram (distribution), anything else → bar of
            // top-N value counts. The user can switch chart kind in the
            // params form and the live preview re-renders in place.
            // Note: live-grid's shortType() normalises double/float/decimal
            // → "num" before this prop arrives, so check for "num" first.
            const t = (a.columnType ?? "").toLowerCase();
            const isNumeric =
              t === "num" ||
              t === "int" ||
              t.includes("int") ||
              t.includes("float") ||
              t.includes("double") ||
              t.includes("decimal");
            return {
              kind: isNumeric ? "histogram" : "bar_counts",
              x: a.column,
              title: `${a.column} — distribution`,
              format: "png",
            };
          }
          case "visualize_as": {
            // Pre-fill the clicked column into the step's most-fitting
            // column_ref param. Heuristic:
            //   1. If the column is numeric, prefer a param whose spec
            //      lists numeric columnTypes (typically `value` / `y`).
            //   2. Otherwise prefer a param without a numeric constraint
            //      (typically `label` / `stage` / `group` / `x`).
            //   3. Always set `title` if the manifest has one.
            // The user lands on the params form and fills in any
            // remaining required slots (most chart steps need 2 columns).
            const t = (a.columnType ?? "").toLowerCase();
            const isNumeric =
              t === "num" ||
              t === "int" ||
              t.includes("int") ||
              t.includes("float") ||
              t.includes("double") ||
              t.includes("decimal");
            const params: Record<string, unknown> = {};
            const paramSpecs = manifest.params || {};
            // Find the best column_ref slot to pre-fill.
            const colRefEntries = Object.entries(paramSpecs).filter(
              ([, spec]) => (spec as { type?: string }).type === "column_ref",
            );
            const numericSlot = colRefEntries.find(
              ([, spec]) => {
                const ct = (spec as { columnTypes?: string[] }).columnTypes;
                return ct && ct.some((x) => /int|double|float|decimal/i.test(x));
              },
            );
            const categoricalSlot = colRefEntries.find(
              ([, spec]) => {
                const ct = (spec as { columnTypes?: string[] }).columnTypes;
                return !ct || !ct.some((x) => /int|double|float|decimal/i.test(x));
              },
            );
            const slot = isNumeric
              ? (numericSlot ?? categoricalSlot ?? colRefEntries[0])
              : (categoricalSlot ?? numericSlot ?? colRefEntries[0]);
            if (slot) {
              params[slot[0]] = a.column;
            }
            if ("title" in paramSpecs) {
              params["title"] = `${a.column} — ${manifest.label}`;
            }
            return params;
          }
        }
      })();
      try {
        const prevDoc = doc;
        // Column actions originate from the FOCUSED step (the column menu
        // operates on what's visible there) — insert the new step right
        // after that focus so the cast / filter / rename happens at the
        // exact point the user invoked it. Without this, casting from an
        // earlier step's column menu would mis-place the cast at the end
        // of the chain (the bug that surfaced "customer_id not found").
        const { doc: next, nodeId } = insertStepAfter(doc, manifest, params, focusedId);
        updateDoc(next);
        setFocusedId(nodeId);
        setTab("params");
        // Optimistic schema projection: for predictable, non-failing column
        // edits (rename, drop, reorder) we mutate the in-memory preview to
        // match the expected post-step shape *immediately*. The next
        // successful recompile will replace this projection wholesale; in
        // the meantime the grid shows the new column layout instead of the
        // stale one. We don't optimistic-project cast (can fail on bad
        // values) or filter/group/derive (need actual computation).
        if (a.kind === "rename" || a.kind === "drop" || a.kind === "reorder") {
          setPreview((prev) => {
            if (!prev) return prev;
            if (a.kind === "rename") {
              const cols = prev.columns.map((c) =>
                c.name === a.column ? { ...c, name: a.to } : c,
              );
              const rows = prev.rows.map((r) => {
                if (!(a.column in r)) return r;
                const { [a.column]: v, ...rest } = r;
                return { ...rest, [a.to]: v };
              });
              return { ...prev, columns: cols, rows };
            }
            if (a.kind === "drop") {
              const cols = prev.columns.filter((c) => c.name !== a.column);
              const rows = prev.rows.map((r) => {
                if (!(a.column in r)) return r;
                const { [a.column]: _drop, ...rest } = r;
                return rest;
              });
              return { ...prev, columns: cols, rows };
            }
            // reorder: mirror the SQL `SELECT ordered..., * EXCLUDE (...)
            // FROM in` semantic — listed columns first (in order), then any
            // remaining input columns (preserving original input order).
            // Row objects don't have a JS-iteration-order guarantee that
            // matters to consumers (LiveGrid reads cells via columns[].name)
            // so we leave row dicts untouched; only columns reorders.
            const byName = new Map(prev.columns.map((c) => [c.name, c]));
            const ordered = a.order.flatMap((n) => {
              const c = byName.get(n);
              return c ? [c] : [];
            });
            const orderedSet = new Set(a.order);
            const remaining = prev.columns.filter((c) => !orderedSet.has(c.name));
            return { ...prev, columns: [...ordered, ...remaining] };
          });
        }
        // Optimistic toast with one-click undo at the click site. Without
        // this the user thinks "where did my row go?" after an unintended
        // ⌘+click filter and has to scan to the strip to find the new step.
        toast.success(`✨ Added ${manifest.label}`, {
          duration: 4500,
          action: { label: "Undo", onClick: () => updateDoc(prevDoc) },
        });
      } catch (e) {
        toast.error((e as Error).message);
      }
    },
    [doc, updateDoc, manifestsById, currentSchema, setFocusedId, setTab],
  );

  const handleCellQuickFilter = useCallback(
    (column: string, value: unknown, mode: "eq" | "neq") => {
      handleColumnAction({ kind: mode === "eq" ? "filter_eq" : "filter_neq", column, value });
    },
    [handleColumnAction],
  );

  const handleApplySuggestion = useCallback(
    (s: Suggestion) => {
      handleColumnAction(s.action);
      toast.success(`✨ ${s.applyLabel} applied`);
    },
    [handleColumnAction],
  );

  // ---- Add dataset ----
  const [datasetPickerOpen, setDatasetPickerOpen] = useState(false);
  const datasetPickerRef = useRef<HTMLDivElement>(null);
  // Close on click-outside + Escape so the picker doesn't trap interactions.
  useEffect(() => {
    if (!datasetPickerOpen) return;
    const onClick = (e: MouseEvent) => {
      if (datasetPickerRef.current && !datasetPickerRef.current.contains(e.target as Node)) {
        setDatasetPickerOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDatasetPickerOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [datasetPickerOpen]);
  const handleAddDataset = useCallback(
    (d: Dataset) => {
      if (!doc) return;
      const refId = datasetRefId(d);
      if (doc.datasets.some((x) => x.id === refId)) {
        toast(`Already in this pipeline`);
        return;
      }
      const uri = d.storageUri ?? d.sourceUri;
      const connector = d.storageUri ? "parquet" : d.connector;
      const next: PipelineDocument = {
        ...doc,
        datasets: [
          ...doc.datasets,
          { id: refId, connector, uri, label: d.name, options: {} },
        ],
      };
      updateDoc(next);
      setFocusedId(refId);
      setTab("hints");
      setDatasetPickerOpen(false);
      toast.success(`📥 Added dataset "${d.name}"`);
    },
    [doc, updateDoc],
  );

  // ---- Run on backend ----
  const [run, setRun] = useState<RunOut | null>(null);
  const [runProgress, setRunProgress] = useState<{ status?: string; stage?: string }>({});
  const [outputPage, setOutputPage] = useState<RunOutputPage | null>(null);
  const wsTeardown = useRef<(() => void) | null>(null);
  const [runHistoryRefresh, setRunHistoryRefresh] = useState(0);
  useEffect(() => () => wsTeardown.current?.(), []);

  const runMutation = useMutation({
    mutationFn: async () => api.startRun(pipelineId),
    onSuccess: (r) => {
      setRun(r);
      setRunProgress({ status: r.status });
      setOutputPage(null);
      setRunHistoryRefresh((n) => n + 1);
      // Adaptive UI: a run is +3 toward Builder promotion.
      recordAction(3);
      toast.success(`▶️ Run queued (${r.id.slice(-8)})`);
      wsTeardown.current?.();
      wsTeardown.current = subscribe(
        `/ws/runs/${r.id}`,
        async (msg) => {
          const p = msg.payload as { status?: string; stage?: string };
          setRunProgress(p);
          if (p.status === "succeeded") {
            const out = await api.getRunOutput(r.id, 0, 200);
            setOutputPage(out);
            setRunHistoryRefresh((n) => n + 1);
            toast.success(`✅ Run finished (${out.totalRows.toLocaleString()} rows)`);
          } else if (p.status === "failed") {
            setRunHistoryRefresh((n) => n + 1);
            toast.error(`❌ Run failed`);
          }
        },
      );
    },
    onError: (e: Error) => toast.error(`Run failed: ${e.message}`),
  });

  // ---- Selected node for params tab ----
  const selectedNode = useMemo(
    () => doc?.nodes.find((n) => n.id === focusedId) ?? null,
    [doc, focusedId],
  );
  const selectedManifest = selectedNode ? manifestsById[selectedNode.step] : undefined;

  const upstreamColumns = useMemo(() => {
    if (!selectedNode || !selectedManifest) return {} as Record<string, string[]>;
    const result: Record<string, string[]> = {};
    const ports = selectedManifest.io.inputs.ports ?? ["in"];
    for (const port of ports) {
      const ref = selectedNode.inputs[port];
      if (!ref) {
        result[port] = [];
        continue;
      }
      const sch = schemas[ref.ref];
      result[port] = sch ? Object.keys(sch) : [];
    }
    return result;
  }, [selectedNode, selectedManifest, schemas]);

  // Auto-switch to Params when a node is selected; Hints when a dataset is selected
  useEffect(() => {
    if (selectedNode) setTab("params");
    else if (isFocusedDataset) setTab("hints");
  }, [selectedNode, isFocusedDataset]);

  // ---- row counts per step (for the strip) ----
  const rowCounts = useMemo<Record<string, number | null>>(() => {
    const out: Record<string, number | null> = {};
    if (focusedId && preview) {
      out[focusedId] = preview.rowCount;
    }
    if (focusedDatasetReal) {
      out[datasetRefId(focusedDatasetReal)] = focusedDatasetReal.rowCount ?? null;
    }
    return out;
  }, [focusedId, preview, focusedDatasetReal]);

  // ---- Phase A Layer 1: latest run's per-node metrics ----
  // Drives the canvas run-state strip + clock chip + freshness halo.
  // Fetches the latest run on mount and after each re-run; gracefully
  // degrades to no overlay when there's no run history yet.
  const [latestRun, setLatestRun] = useState<RunOut | null>(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const runs = await api.listRuns(pipelineId);
        if (cancelled) return;
        // Prefer the most recent succeeded; fall back to most recent overall
        // so the user can see "failed at <step>" cues.
        const sorted = [...runs].sort(
          (a, b) =>
            new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
        const succ = sorted.find((r) => r.status === "succeeded");
        setLatestRun(succ ?? sorted[0] ?? null);
      } catch {
        // 404 / transient — leave latestRun null; canvas just renders
        // without overlays.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pipelineId, runHistoryRefresh]);

  // When a run finishes via the local mutation flow, prefer THAT run as
  // the source of nodeMetrics — it's the freshest available without a
  // refetch. Otherwise fall back to listRuns()-fetched latestRun.
  const effectiveRun = run?.status === "succeeded" || run?.status === "failed"
    ? run
    : latestRun;

  // ---- Phase A Layer 3: column trace ----
  // Hover any column header in the live grid → fetch lineage → dim every
  // canvas node NOT in the resulting subgraph. Cancellation is via a
  // generation counter so a slow request doesn't overwrite a newer one.
  const [tracedNodeIds, setTracedNodeIds] = useState<Set<string> | null>(null);
  const traceGenRef = useRef(0);
  const handleColumnTrace = useCallback(
    async (column: string) => {
      if (!focusedId) return;
      const myGen = ++traceGenRef.current;
      try {
        const res = await api.getColumnLineage(pipelineId, focusedId, column);
        if (myGen !== traceGenRef.current) return;
        const ids = new Set<string>(res.nodes.map((n) => n.node_id));
        // Always include the focused node itself so the source of the
        // hover stays bright.
        ids.add(focusedId);
        setTracedNodeIds(ids);
      } catch {
        // Endpoint missing or column has no declared dependencies — leave
        // the canvas un-dimmed.
      }
    },
    [pipelineId, focusedId],
  );
  const handleColumnTraceClear = useCallback(() => {
    traceGenRef.current++;   // cancel any in-flight trace
    setTracedNodeIds(null);
  }, []);

  // ---- Phase A Layer 6: Sankey volume view toggle ----
  // Parallel view to the structural xyflow canvas. The user can toggle
  // between "Structure" (today's editor) and "Volume" (Sankey, read-only)
  // via the floating button in the canvas's top-right corner.
  const [canvasMode, setCanvasMode] = useState<"structure" | "volume">(
    "structure",
  );

  // ---- Phase A Layer 4: group selection + editing ----
  // xyflow multi-selection mirror; the floating action bar uses this.
  const [selectedStepIds, setSelectedStepIds] = useState<string[]>([]);
  // The group currently being edited (clicked title chip → opens popover).
  const [editingGroup, setEditingGroup] = useState<{
    id: string;
    anchor: { x: number; y: number };
  } | null>(null);
  // Group bboxes published by GraphCanvas after each layout — kept here
  // so right-click "Add to group" can know the geometry, even though the
  // primary path is xyflow's drag-end auto-membership inside GraphCanvas.
  const [groupBboxes, setGroupBboxes] = useState<
    Record<string, { x: number; y: number; w: number; h: number }>
  >({});

  type DocGroup = {
    id: string;
    label: string;
    node_ids: string[];
    parent_group_id?: string | null;
    ui?: {
      color?: string | null;
      collapsed?: boolean;
      freshness?: { sla: string; warn_at?: string | null } | null;
    };
  };

  const docGroups = ((doc as unknown as { groups?: DocGroup[] })?.groups ?? []);

  const handleSetGroups = useCallback(
    (next: DocGroup[]) => {
      if (!doc) return;
      updateDoc({ ...doc, groups: next } as PipelineDocument);
    },
    [doc, updateDoc],
  );

  // Compute the transitive set of step ids for each existing group:
  // direct members ∪ members of all descendant groups. Used to find the
  // smallest group that fully contains a selection — that group becomes
  // the new sub-group's parent.
  const transitiveMembers = useMemo<Record<string, Set<string>>>(() => {
    const childrenOf: Record<string, string[]> = {};
    for (const g of docGroups) {
      const pid = g.parent_group_id ?? null;
      if (pid) (childrenOf[pid] ??= []).push(g.id);
    }
    const groupById = new Map(docGroups.map((g) => [g.id, g]));
    const cache: Record<string, Set<string>> = {};
    function compute(gid: string, seen = new Set<string>()): Set<string> {
      if (cache[gid]) return cache[gid];
      if (seen.has(gid)) return new Set();
      seen.add(gid);
      const g = groupById.get(gid);
      const out = new Set<string>(g?.node_ids ?? []);
      for (const cid of (childrenOf[gid] ?? [])) {
        for (const sid of compute(cid, seen)) out.add(sid);
      }
      cache[gid] = out;
      return out;
    }
    for (const g of docGroups) compute(g.id);
    return cache;
  }, [docGroups]);

  const handleCreateGroup = useCallback(
    (label: string, nodeIds: string[]) => {
      // Find the smallest existing group that fully contains the
      // selection; that becomes the new group's parent. "Smallest" =
      // fewest transitive members, so a sub-cluster of the smaller of
      // two enclosing candidates gets picked. None = top-level group.
      let parentId: string | null = null;
      let parentSize = Number.POSITIVE_INFINITY;
      for (const g of docGroups) {
        const members = transitiveMembers[g.id];
        if (!members) continue;
        const containsAll = nodeIds.every((id) => members.has(id));
        if (containsAll && members.size < parentSize) {
          parentSize = members.size;
          parentId = g.id;
        }
      }
      const fresh: DocGroup = {
        id: `g_${Math.random().toString(36).slice(2, 10)}`,
        label,
        node_ids: nodeIds,
        parent_group_id: parentId,
        ui: { collapsed: false },
      };
      // Remove the moved nodes from ANY ancestor group's direct
      // members. The new sub-group now owns them directly; the parent
      // still contains them transitively via the sub-group, so the
      // visual stays the same but the data model is clean (no node is
      // listed twice).
      const movedSet = new Set(nodeIds);
      const updated = docGroups.map((g) => ({
        ...g,
        node_ids: g.node_ids.filter((id) => !movedSet.has(id)),
      }));
      handleSetGroups([...updated, fresh]);
      setSelectedStepIds([]);
    },
    [docGroups, handleSetGroups, transitiveMembers],
  );

  const handleAddToGroup = useCallback(
    (groupId: string, nodeIds: string[]) => {
      handleSetGroups(
        docGroups.map((g) =>
          g.id === groupId
            ? {
                ...g,
                node_ids: Array.from(new Set([...g.node_ids, ...nodeIds])),
              }
            : g,
        ),
      );
      setSelectedStepIds([]);
    },
    [docGroups, handleSetGroups],
  );

  const handleSaveGroup = useCallback(
    (next: DocGroup) => {
      handleSetGroups(docGroups.map((g) => (g.id === next.id ? next : g)));
    },
    [docGroups, handleSetGroups],
  );

  const handleDeleteGroup = useCallback(
    (groupId: string) => {
      handleSetGroups(docGroups.filter((g) => g.id !== groupId));
    },
    [docGroups, handleSetGroups],
  );

  // Stable callbacks for GraphCanvas — without `useCallback` these would
  // get a new identity every render, invalidating the canvas's
  // `useMemo` for `buildGraph`, which would re-fire the group-bbox
  // useEffect, which would call setGroupBboxes, which would re-render —
  // infinite loop.
  const handleGroupClick = useCallback(
    (groupId: string, anchor: { x: number; y: number }) => {
      setEditingGroup({ id: groupId, anchor });
    },
    [],
  );
  const handleGroupBboxesChanged = useCallback(
    (
      bboxes: Record<string, { x: number; y: number; w: number; h: number }>,
    ) => {
      setGroupBboxes(bboxes);
    },
    [],
  );

  // ---- Phase A Layer 2: per-node + per-group freshness halos ----
  // Fetched server-side; the backend combines the freshness policies
  // declared in the pipeline document with the latest succeeded run's
  // finishedAt to compute a state per node + per group.
  const [nodeFreshness, setNodeFreshness] = useState<
    Record<string, "fresh" | "due" | "stale" | "never">
  >({});
  const [groupFreshness, setGroupFreshness] = useState<
    Record<string, "fresh" | "due" | "stale" | "never">
  >({});
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.getFreshness(pipelineId);
        if (!cancelled) {
          setNodeFreshness(r.states ?? {});
          setGroupFreshness(r.group_states ?? {});
        }
      } catch {
        // Endpoint missing on older backends → no halos. Acceptable.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pipelineId, runHistoryRefresh, doc]);   // doc dep so re-saving groups refetches

  const nodeMetricsForCanvas = useMemo<
    Record<string, import("@/components/canvas/graph-canvas").NodeRunMetrics>
  >(() => {
    if (!effectiveRun?.nodeMetrics) return {};
    // Backend stores datetimes in SQLite, which drops the tzinfo. Pydantic
    // then serializes them naive (no `+00:00` marker), so JS `new Date()`
    // parses them as LOCAL — off by the user's UTC offset. We know the
    // backend writes UTC, so force the Z if it's missing.
    const parseUtcMs = (s: string | null | undefined): number | null => {
      if (!s) return null;
      const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s);
      return new Date(hasTz ? s : `${s}Z`).getTime();
    };
    const finishedAtMs = parseUtcMs(effectiveRun.finishedAt);
    const out: Record<string, import("@/components/canvas/graph-canvas").NodeRunMetrics> = {};
    for (const [nodeId, m] of Object.entries(effectiveRun.nodeMetrics)) {
      const status = (m as { status?: string }).status as
        | "success" | "failed" | "stale" | "never" | "running"
        | undefined;
      if (!status) continue;
      out[nodeId] = {
        status,
        rows_out: (m as { rows_out?: number | null }).rows_out ?? null,
        elapsed_ms: (m as { elapsed_ms?: number | null }).elapsed_ms ?? null,
        finished_at_ms: finishedAtMs,
      };
    }
    return out;
  }, [effectiveRun]);

  if (!doc) {
    // Differentiate "still loading" from "API said 404" — the previous
    // version showed PositiveLoader for both, so a wrong / stale URL
    // hung forever on "Loading pipeline… NNs elapsed". The 404 (or any
    // hard fetch error) needs an actionable not-found state with a
    // path back to the list.
    if (pipeline.error) {
      const msg = (pipeline.error as Error).message || "Pipeline could not be loaded.";
      const looks404 = /404|not found/i.test(msg);
      return (
        <main id="main" className="flex flex-1 items-center justify-center p-8">
          <div className="max-w-md text-center space-y-3">
            <div className="text-4xl" aria-hidden>🛤</div>
            <h1 className="text-lg font-semibold">
              {looks404 ? "Pipeline not found" : "Couldn’t load pipeline"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {looks404
                ? "This pipeline doesn’t exist (or was deleted). It may have been a demo that got overwritten."
                : msg}
            </p>
            <Link
              href="/pipelines"
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              ← Back to pipelines
            </Link>
          </div>
        </main>
      );
    }
    return (
      <main id="main" className="flex flex-1 items-center justify-center">
        <PositiveLoader variant="rendering" primary="Loading pipeline…" />
      </main>
    );
  }

  return (
    // overflow-hidden + h-screen pins the editor to the viewport so the
    // bottom strip / graph stays glued to the bottom of the browser
    // window. Without overflow-hidden, a tall data grid would push the
    // strip below the visible area (it'd be there, just not on screen).
    <main className="flex flex-col h-screen overflow-hidden">
      {/* Top bar */}
      {/* `relative z-30` so the toolbar's stacking context sits above the
          workspace below. Without it, `backdrop-blur` traps the Add-dataset
          dropdown's z-[60] inside the header's context — the dropdown
          renders visually but LiveGrid's transparent empty-state overlay
          (later in document order, same z=auto in root) silently swallows
          clicks on the part of the dropdown that overflows past the toolbar. */}
      <header className="relative z-30 border-b border-border bg-background/80 backdrop-blur px-4 py-2 flex items-center gap-3 shrink-0">
        <Link
          href="/pipelines"
          className={buttonVariants({ variant: "ghost", size: "sm" })}
          aria-label="Back to pipelines"
        >
          ←
        </Link>
        <span className="text-xl select-none" aria-hidden>🛤</span>
        <input
          type="text"
          value={doc.name}
          onChange={(e) => updateDoc({ ...doc, name: e.target.value })}
          className="text-base font-medium bg-transparent outline-none border-b border-transparent focus:border-foreground/30 px-1 py-0.5 min-w-[180px]"
        />
        <SaveIndicator dirty={dirty} pending={saveMutation.isPending} />
        <span className="text-[11px] text-muted-foreground/60 tabular-nums">v{etag}</span>
        <PipelineTags
          pipelineId={pipelineId}
          initialTags={(doc as PipelineDocument & { tags?: string[] }).tags ?? []}
          etag={etag}
          onChange={(tags) => updateDoc({ ...(doc as PipelineDocument & { tags?: string[] }), tags } as PipelineDocument)}
        />

        {/* Explicit Save (labeled checkpoint) — survives history pruning,
            unlike auto-saves. Cmd/Ctrl-S also wired up below. */}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setSaveDialogOpen(true)}
          title="Save a labeled checkpoint (⌘S) — survives autosave history pruning"
        >
          💾 Save
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setSaveAsDialogOpen(true)}
          title="Save As — clone this pipeline to a new one"
        >
          📋 Save As
        </Button>

        <Button size="sm" variant="ghost" onClick={undo} disabled={undoLen === 0} title="Undo (⌘Z)">
          ↩️
        </Button>
        <Button size="sm" variant="ghost" onClick={redo} disabled={redoLen === 0} title="Redo (⌘⇧Z)">
          ↪️
        </Button>

        <div className="flex-1" />

        <div className="relative" ref={datasetPickerRef}>
          <Button
            variant="outline"
            onClick={() => setDatasetPickerOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={datasetPickerOpen}
          >
            📥 Add dataset
          </Button>
          {datasetPickerOpen && (
            <div
              role="menu"
              className="absolute right-0 top-[calc(100%+4px)] w-[280px] max-h-[320px] overflow-auto z-[60] rounded-md border border-border bg-popover shadow-lg p-1"
            >
              {(datasetsQ.data ?? []).length === 0 ? (
                <div className="text-xs text-muted-foreground p-3 text-center">
                  No datasets yet — <Link className="underline" href="/datasets">upload one</Link>.
                </div>
              ) : (
                (datasetsQ.data ?? []).map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => handleAddDataset(d)}
                    className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-muted/60 flex items-center gap-2"
                  >
                    <span aria-hidden>📊</span>
                    <span className="truncate">{d.name}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">
                      {fmtInt(d.rowCount)}r
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Lineage opt-in: when checked, the pipeline doc's
            metadata.trackLineage flips on, and the executor records each
            output row's source-row indices. Cost: ~10–30% slower run +
            extra storage for the lineage map. The grid then shows a 🔍
            button on each output row to trace it back. */}
        <label
          className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer select-none px-1"
          title="Record per-row source links so you can click 🔍 in the run output to trace any value back to its source dataset row. Adds ~10–30% to run time."
        >
          <input
            type="checkbox"
            checked={Boolean(doc.metadata?.trackLineage)}
            onChange={(e) => {
              const next = { ...doc, metadata: { ...(doc.metadata ?? {}), trackLineage: e.target.checked } };
              updateDoc(next);
            }}
          />
          🔍 lineage
        </label>

        {/* 🧪 Sampling — opens the per-flow sampling-method picker. */}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setSamplingOpen(true)}
          title="Choose how the editor preview draws sample rows for this pipeline"
        >
          🧪 {(() => {
            const s = doc.metadata?.sampling as SamplingConfig | undefined;
            if (!s) return "head";
            return s.method;
          })()}
        </Button>

        {/* 🪆 Publish-as-step — turns this pipeline into a reusable
            building block that appears in every other pipeline's
            picker. The icon glows when already published. */}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setPublishOpen(true)}
          title={
            doc.metadata?.publishedAsStep
              ? "Edit the published-step settings — consumers will see your changes after they upgrade their pinned version."
              : "Publish this pipeline as a reusable step — it'll appear in every other pipeline's picker."
          }
        >
          🪆 {doc.metadata?.publishedAsStep ? "Published" : "Publish"}
        </Button>

        <Button
          data-tour="editor-run"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending || doc.nodes.length === 0}
          title="Run the full pipeline on the backend (writes to disk)"
          className="!bg-emerald-500 !text-emerald-950 hover:!bg-emerald-400"
        >
          {runMutation.isPending || runProgress.status === "queued" || runProgress.status === "running"
            ? "⏳ Running…"
            : "▶️ Run on backend"}
        </Button>

        <RunHistory
          pipelineId={pipelineId}
          refreshKey={runHistoryRefresh}
          onView={async (r) => {
            try {
              const out = await api.getRunOutput(r.id, 0, 200);
              setOutputPage(out);
              setRun(r);
              setRunProgress({ status: r.status });
            } catch (e) {
              toast.error(`Couldn't load run: ${(e as Error).message}`);
            }
          }}
        />

        {/* 🛤 Strip / 🕸 Graph toggle for the bottom canvas. Strip is the
            default linear view; Graph is the React Flow DAG for branched
            pipelines (joins, unions, sub-pipelines). */}
        <div className="inline-flex rounded-md border border-border overflow-hidden text-xs">
          <button
            type="button"
            onClick={() => setCanvasView("strip")}
            aria-pressed={canvasView === "strip"}
            className={[
              "px-2 py-1 transition-colors",
              canvasView === "strip"
                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                : "text-muted-foreground hover:bg-muted/60",
            ].join(" ")}
            title="Linear strip view (good for short, linear pipelines)"
          >
            🛤 Strip
          </button>
          <button
            type="button"
            onClick={() => setCanvasView("graph")}
            aria-pressed={canvasView === "graph"}
            className={[
              "px-2 py-1 transition-colors border-l border-border",
              canvasView === "graph"
                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                : "text-muted-foreground hover:bg-muted/60",
            ].join(" ")}
            title="Graph view (shows the real DAG; good for joins / unions / sub-pipelines)"
          >
            🕸 Graph
          </button>
        </div>

        <SuggestNextButton
          pipelineId={pipelineId}
          focusedNodeId={focusedId}
          // Schema is keyed by node id; the suggest endpoint reads
          // column-name → logical-type from the focused node so the AI
          // can refer to columns by name.
          focusedSchema={focusedId ? (schemas[focusedId] ?? {}) : {}}
          onApply={(suggestion) => {
            if (!doc) return;
            const manifest = manifestsById[suggestion.step_id];
            if (!manifest) {
              toast.error(`Step '${suggestion.step_id}' is not registered`);
              return;
            }
            try {
              // AI suggestions land at the focused position too — same
              // mental model as everywhere else.
              const { doc: next, nodeId } = insertStepAfter(
                doc,
                manifest,
                suggestion.params,
                focusedId,
              );
              updateDoc(next);
              setFocusedId(nodeId);
              setTab("params");
            } catch (e) {
              toast.error(`Couldn't add step: ${(e as Error).message}`);
            }
          }}
        />
        <ExplainPipelineButton pipelineId={pipelineId} />
        <ReviewPanel pipelineId={pipelineId} />
        <CompareButton pipelineId={pipelineId} />
        <ShareDialog pipelineId={pipelineId} pipelineName={doc?.name ?? ""} />
        {expertise.isAtLeast("engineer") && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSqlViewOpen(true)}
            title="View compiled SQL (⌘⇧S)"
            aria-label="View compiled SQL"
          >
            { } SQL
          </Button>
        )}
        <ExportMenu pipelineId={pipelineId} />

        <Button
          size="sm"
          variant="ghost"
          onClick={() => setEditorTourOpen(true)}
          title="Replay the 60-second editor tour"
          aria-label="Replay editor tour"
        >
          🧭
        </Button>
      </header>

      {/* Workspace: top = grid, right = side panel, bottom = strip */}
      <div className="flex flex-1 min-h-0">
        {/* Left/main column: grid + diff strip + pipeline strip */}
        <section className="flex-1 flex flex-col min-h-0 min-w-0">
          {diff && (
            <DiffStrip diff={diff} />
          )}
          {(() => {
            // Diagnostic 3-way toggle for joins. Mounts above the grid
            // ONLY when the focused step is a join — for any other
            // step the toggle is irrelevant and would just add noise.
            const fNode = focusedId
              ? doc?.nodes.find((n) => n.id === focusedId)
              : null;
            if (fNode?.step !== "join") return null;
            const opts: Array<{
              id: "matched" | "unmatched_left" | "unmatched_right";
              label: string;
              hint: string;
            }> = [
              { id: "matched", label: "✓ matched", hint: "The joined output — what the rest of the pipeline sees." },
              { id: "unmatched_left", label: "← unmatched-L", hint: "Left rows with NO match on the right. Diagnostic only — not persisted in the doc." },
              { id: "unmatched_right", label: "unmatched-R →", hint: "Right rows with NO match on the left. Diagnostic only — not persisted in the doc." },
            ];
            return (
              <div className="shrink-0 border-b border-border/60 bg-card/40 px-3 py-1.5 flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  🔎 Join view
                </span>
                <div className="flex items-center gap-1">
                  {opts.map((o) => {
                    const active = joinViewMode === o.id;
                    return (
                      <button
                        key={o.id}
                        type="button"
                        onClick={() => setJoinViewMode(o.id)}
                        title={o.hint}
                        className={[
                          "text-[11px] px-2 py-0.5 rounded-md border transition-colors font-mono",
                          active
                            ? "border-emerald-400/70 bg-emerald-50/80 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-200"
                            : "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground",
                        ].join(" ")}
                      >
                        {o.label}
                      </button>
                    );
                  })}
                </div>
                {joinViewMode !== "matched" && (
                  <span className="text-[10px] text-amber-700 dark:text-amber-300 italic">
                    diagnostic only — pipeline still emits the matched output
                  </span>
                )}
              </div>
            );
          })()}
          <div className="flex-1 min-h-0">
            <LiveGrid
              columns={gridData.columns}
              rows={gridData.rows}
              totalRows={gridData.totalRows}
              sampleRows={preview?.sampleRows ?? 100_000}
              loading={gridData.loading}
              elapsedMs={gridData.elapsedMs}
              ranLocally={preview ? preview.ranLocally : true}
              downstreamImpact={downstreamImpact}
              nanOrigins={
                // NaN-origin sidecar for the focused step on the most
                // recent backend run. Only surfaces in the grid when the
                // displayed rows come from a backend run path (the row
                // indices align with the persisted parquet). Empty / no
                // chip when the user is in the WASM live-preview path
                // — see internal/proposals/NULL_AND_NAN_DISPLAY.md
                // "Where the implementation will differ" #2.
                // openapi-typescript widens the per-entry type to
                // {[k:string]: unknown}[] because the backend Pydantic
                // model uses `list[dict[str, Any]]`. The runtime shape
                // is locked by the executor's `_nan_origin_to_dict` and
                // mirrored by `NanOriginEntry` in live-grid.tsx.
                preview?.ranLocally === false && focusedId
                  ? (effectiveRun?.nanOrigins?.[focusedId] as unknown as
                      import("@/components/grid/live-grid").NanOriginEntry[]
                      | undefined)
                  : undefined
              }
              onColumnAction={handleColumnAction}
              onCellQuickFilter={handleCellQuickFilter}
              onColumnTrace={handleColumnTrace}
              onColumnTraceClear={handleColumnTraceClear}
              highlights={highlights}
              annotations={focusedDatasetReal?.annotations ?? undefined}
              onSaveAnnotation={
                focusedDatasetReal
                  ? async (col, text) => {
                      const next = { ...(focusedDatasetReal.annotations ?? {}) };
                      if (text.trim()) next[col] = text.trim();
                      else delete next[col];
                      try {
                        await api.updateAnnotations(focusedDatasetReal.id, next);
                        queryClient.invalidateQueries({ queryKey: ["datasets"] });
                        toast.success(text.trim() ? "📝 Saved" : "📝 Cleared");
                      } catch (e) {
                        toast.error(`Save failed: ${(e as Error).message}`);
                      }
                    }
                  : undefined
              }
              emptyHint={
                doc.datasets.length === 0 ? (
                  <div className="max-w-sm">
                    <div className="text-6xl mb-3">🌱</div>
                    <p className="font-medium mb-1">Empty canvas</p>
                    <p className="text-xs">
                      Click <strong>📥 Add dataset</strong> in the top-right to bring data in.
                      The grid lights up immediately so you can shape it.
                    </p>
                  </div>
                ) : (() => {
                  // Chart-first steps mount StepImageOrFallback IMMEDIATELY
                  // when focused — no detour through previewError, no
                  // 600ms grace, no risk of flashing the "doesn't have a
                  // live preview" message. The user sees a positive
                  // "Rendering preview…" state from the moment they click
                  // until the chart appears.
                  const fNode = focusedId
                    ? doc?.nodes.find((n) => n.id === focusedId)
                    : null;
                  if (fNode && isChartFirstStep(manifestsById[fNode.step])) {
                    // Resolve the upstream rowCount for the density
                    // banner. Chart steps preserve rows, so the chart
                    // node's last preview rowCount equals its input
                    // count when known. Fall back to the root dataset's
                    // rowCount (worst-case) when no preview has run.
                    let upstreamRows: number | null = null;
                    if (preview && previewedFocusRef.current === fNode.id) {
                      upstreamRows = preview.rowCount ?? null;
                    }
                    if (upstreamRows == null) {
                      // Walk back to the root dataset to find a count.
                      let cur: string | undefined = Object.values(fNode.inputs)[0]?.ref;
                      const seen = new Set<string>();
                      while (cur && !seen.has(cur)) {
                        seen.add(cur);
                        const ds = doc.datasets.find((d) => d.id === cur);
                        if (ds) {
                          const real = (datasetsQ.data ?? []).find(
                            (d) => datasetRefId(d) === cur,
                          );
                          upstreamRows = real?.rowCount ?? null;
                          break;
                        }
                        const upNode = doc.nodes.find((n) => n.id === cur);
                        if (!upNode) break;
                        cur = Object.values(upNode.inputs)[0]?.ref;
                      }
                    }
                    const dismissed = dismissedDensityWarnings.has(fNode.id);
                    const fManifest = manifestsById[fNode.step];
                    return (
                      <div className="flex flex-col items-center w-full">
                        {!dismissed && upstreamRows != null && fManifest && (
                          <ChartDensityWarning
                            manifest={fManifest}
                            params={fNode.params}
                            upstreamRowCount={upstreamRows}
                            onSample={() => {
                              // Resolve the same threshold the warning
                              // is showing to size the random sample.
                              const r = fManifest.recommendedMaxRows;
                              let n = 5000;
                              if (typeof r === "number") n = r;
                              else if (r && typeof r === "object") {
                                const k = String(fNode.params?.kind ?? "");
                                // `(k && r[k])` is `"" | number` because `k`
                                // is a string. Force-resolve to number; the
                                // empty-string short-circuit means "fall
                                // through to default".
                                const picked = k ? r[k] : undefined;
                                n = (typeof picked === "number" ? picked : undefined)
                                  ?? r._default ?? n;
                              }
                              const meta = {
                                ...(doc.metadata ?? {}),
                                sampling: { method: "random" as const, size: n },
                              };
                              updateDoc({ ...doc, metadata: meta });
                              toast.success(
                                `Sampling reduced to ${n.toLocaleString()} random rows. ⌘Z to revert.`,
                              );
                              setDismissedDensityWarnings((s) =>
                                new Set(s).add(fNode.id),
                              );
                            }}
                            onDismiss={() =>
                              setDismissedDensityWarnings((s) =>
                                new Set(s).add(fNode.id),
                              )
                            }
                          />
                        )}
                        <StepImageOrFallback
                          pipelineId={pipelineId}
                          nodeId={fNode.id}
                          etag={etag ?? 0}
                          // The fallback receives the actual /preview-step
                          // error (when there is one) so we can pick the
                          // right surface:
                          //  - chart-config error (e.g. "scatter3d needs
                          //    x, y and z") → humanized hint with the
                          //    columns the user can pick from. The
                          //    humanizer recognises these patterns
                          //    (export_to_image kinds + funnel/pareto/
                          //    waterfall) and produces an actionable
                          //    one-liner instead of a generic CTA.
                          //  - genuine "needs backend hop" — keep the
                          //    "▶ Run on backend" affordance.
                          fallback={(err) => {
                            const upRef = Object.values(fNode.inputs)[0]?.ref;
                            const cols = upRef ? Object.keys(schemas[upRef] ?? {}) : [];
                            const h = err ? humanizeSqlError(err.message, cols) : null;
                            if (h && h.recognised && !h.originatesUpstream) {
                              // Per-chart-kind config error — show the
                              // humanized title + hint. No "Run on
                              // backend" button: clicking that won't fix
                              // a missing X/Y/Z param, and surfacing a
                              // wrong CTA misleads the user.
                              return (
                                <div className="max-w-md text-center select-none">
                                  <div className="text-5xl mb-2">⚠️</div>
                                  <p className="text-sm font-medium text-foreground mb-1">
                                    {h.title}
                                  </p>
                                  {h.hint && (
                                    <p className="text-[12px] text-muted-foreground leading-relaxed">
                                      {h.hint}
                                    </p>
                                  )}
                                </div>
                              );
                            }
                            // Default: backend-hop needed (the upstream
                            // chain wasn't sampleable in-memory, or any
                            // unrecognised error shape). One click runs
                            // it on the backend.
                            return (
                              <div className="max-w-sm text-center select-none">
                                <div className="text-5xl mb-3">🎬</div>
                                <p className="text-sm font-medium text-foreground mb-1">
                                  Backend run needed for this chart
                                </p>
                                <p className="text-[12px] text-muted-foreground leading-relaxed mb-3">
                                  The live preview can&apos;t render this chain in
                                  the browser (an upstream step needs the
                                  backend&apos;s Polars engine). One click below
                                  produces the full-fidelity chart.
                                </p>
                                <Button
                                  size="sm"
                                  onClick={() => runMutation.mutate()}
                                  disabled={runMutation.isPending}
                                  className="!bg-emerald-500 !text-emerald-950 hover:!bg-emerald-400"
                                >
                                  {runMutation.isPending ? "⏳ Running…" : "▶ Run on backend"}
                                </Button>
                                <p className="text-[10px] text-muted-foreground/70 mt-2 leading-snug">
                                  Output lands in the run history & shows here on success.
                                </p>
                              </div>
                            );
                          }}
                        />
                      </div>
                    );
                  }
                  return null;
                })() ?? (previewError ? (
                  (() => {
                    // Build the available-columns hint from the upstream
                    // step's schema (the input to the focused node). When
                    // the focused node is a dataset, use its own schema.
                    const focusedNode = focusedId
                      ? doc?.nodes.find((n) => n.id === focusedId)
                      : null;
                    const upstreamRef = focusedNode
                      ? Object.values(focusedNode.inputs)[0]?.ref
                      : focusedId;
                    const cols = upstreamRef ? Object.keys(schemas[upstreamRef] ?? {}) : [];
                    const humanized = humanizeSqlError(previewError, cols);
                    // Only offer AI fix when we have a step manifest to ground
                    // the suggestion. Dataset-focused errors and architectural
                    // problems (Polars-only step picked as terminal) wouldn't
                    // get a useful "change a param" answer; skip the button.
                    const focusedManifest = focusedNode
                      ? manifestsById[focusedNode.step]
                      : undefined;
                    // "Structural" here means the error didn't originate
                    // from the focused step's params — it's upstream
                    // (broken dataset registration, missing input wiring,
                    // Polars-only step compiled for browser, …). The
                    // humanizer flags these via `originatesUpstream`; we
                    // also keep the legacy substring match as a belt-and-
                    // braces fallback for shapes the humanizer hasn't
                    // pattern-matched yet.
                    const isStructural =
                      humanized.originatesUpstream === true ||
                      previewError.includes("has browser engine 'none'");
                    const errorBox = (
                      <div className="max-w-md">
                        <div className="text-5xl mb-2">⚠️</div>
                        <p className="text-destructive font-medium">{humanized.title}</p>
                        {humanized.hint && (
                          <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
                            {humanized.hint}
                          </p>
                        )}
                        <p className="text-[11px] text-muted-foreground/70 mt-2">
                          Edit the focused step's params or ⌘Z to recover.
                        </p>
                        {!humanized.recognised && (
                          <details className="mt-2 text-[10px] text-muted-foreground/60">
                            <summary className="cursor-pointer">Raw error</summary>
                            <pre className="font-mono whitespace-pre-wrap break-all mt-1">{previewError}</pre>
                          </details>
                        )}
                        {focusedNode && focusedManifest && !isStructural && (
                          <SuggestFix
                            manifest={focusedManifest}
                            currentParams={focusedNode.params}
                            availableColumns={cols}
                            errorMessage={previewError}
                            humanizedTitle={humanized.title}
                            onApply={(nextParams) =>
                              updateDoc(setNodeParams(doc, focusedNode.id, nextParams))
                            }
                          />
                        )}
                      </div>
                    );
                    // Polars-only step focused as terminal? Try the live
                    // image preview path first — for export_to_image,
                    // forecast, etc. it renders the actual artifact in
                    // place of the empty grid. Falls through to errorBox
                    // when the step doesn't produce a renderable artifact
                    // or its execute_polars throws.
                    if (isStructural && focusedNode) {
                      return (
                        <StepImageOrFallback
                          pipelineId={pipelineId}
                          nodeId={focusedNode.id}
                          etag={etag ?? 0}
                          fallback={errorBox}
                        />
                      );
                    }
                    return errorBox;
                  })()
                ) : undefined)
              }
            />
          </div>
          {/* Drag handle — only when bottom region is the graph (the
              strip's height is deterministic, so resizing it makes no
              sense). Pointer events for mouse + touch. The handle takes
              4px and is invisible until hover; the cursor change keeps
              it discoverable. */}
          {canvasView === "graph" && (
            <div
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize graph view"
              onPointerDown={(e) => {
                e.preventDefault();
                const el = e.currentTarget as HTMLElement;
                el.setPointerCapture(e.pointerId);
                const startY = e.clientY;
                const startH = graphHeight;
                const onMove = (ev: PointerEvent) => {
                  // Drag UP shrinks the bottom (less graph), DOWN grows.
                  // Wait — we want drag UP to GROW the graph (more bottom
                  // visible), since the handle is ABOVE the graph. So
                  // delta = startY - currentY.
                  const delta = startY - ev.clientY;
                  const next = Math.max(120, Math.min(700, startH + delta));
                  setGraphHeight(next);
                };
                const onUp = (ev: PointerEvent) => {
                  el.releasePointerCapture(ev.pointerId);
                  el.removeEventListener("pointermove", onMove);
                  el.removeEventListener("pointerup", onUp);
                };
                el.addEventListener("pointermove", onMove);
                el.addEventListener("pointerup", onUp);
              }}
              className="h-1 cursor-row-resize bg-transparent hover:bg-emerald-500/40 transition-colors shrink-0 group"
            >
              {/* Visual hint dot row — only on hover */}
              <div className="opacity-0 group-hover:opacity-100 flex items-center justify-center h-full">
                <span className="text-[8px] text-emerald-500/80 leading-none select-none" aria-hidden>
                  ⋯
                </span>
              </div>
            </div>
          )}
          {/* Bottom region: always reserved (min-height for the strip,
              user-resizable for the graph). */}
          <div
            data-tour="editor-strip"
            className={canvasView === "graph" ? "shrink-0" : "shrink-0 min-h-[40px]"}
            style={canvasView === "graph" ? { height: `${graphHeight}px` } : undefined}
          >
            {canvasView === "strip" ? (
              <PipelineStrip
                doc={doc}
                manifests={manifestsById}
                selectedId={focusedId}
                rowCounts={rowCounts}
                // Humanise the per-node compile errors before they hit the
                // tooltip — the raw "Binder Error: Column 'X' in REPLACE
                // list not found in FROM clause" is illegible. We compute
                // available columns from the upstream schema for each
                // node so the tooltip can suggest valid alternatives.
                nodeStatus={(() => {
                  if (Object.keys(nodeStatus).length === 0) return undefined;
                  const out: Record<string, { ok: boolean; error?: string }> = {};
                  for (const node of doc.nodes) {
                    const s = nodeStatus[node.id];
                    if (!s) { out[node.id] = { ok: true }; continue; }
                    if (s.ok) { out[node.id] = { ok: true }; continue; }
                    const upRef = Object.values(node.inputs)[0]?.ref;
                    const cols = upRef ? Object.keys(schemas[upRef] ?? {}) : [];
                    const h = humanizeSqlError(s.error ?? "", cols);
                    out[node.id] = {
                      ok: false,
                      error: [h.title, h.hint].filter(Boolean).join(" "),
                    };
                  }
                  return out;
                })()}
                onSelect={setFocusedId}
                onDelete={(id) => {
                  const next = removeNodeFromDoc(doc, id);
                  updateDoc(next);
                  if (focusedId === id) {
                    const lastNode = next.nodes[next.nodes.length - 1];
                    setFocusedId(lastNode?.id ?? next.datasets[0]?.id ?? null);
                  }
                }}
                onRemoveDataset={(id) => {
                  const next = removeNodeFromDoc(doc, id);
                  updateDoc(next);
                  if (focusedId === id) {
                    setFocusedId(next.datasets[0]?.id ?? null);
                  }
                }}
                onAddStep={handleQuickAddClick}
                onContextMenu={(id, kind, e) => {
                  setStepCtx({ id, kind, x: e.clientX, y: e.clientY });
                }}
              />
            ) : (
              <div className="relative w-full h-full">
                <GraphCanvas
                  doc={doc}
                  manifests={manifestsById}
                  selectedId={focusedId}
                  rowCounts={rowCounts}
                  nodeMetrics={nodeMetricsForCanvas}
                  nodeFreshness={nodeFreshness}
                  groupFreshness={groupFreshness}
                  tracedNodeIds={tracedNodeIds}
                  onSelectionChange={setSelectedStepIds}
                  onGroupClick={handleGroupClick}
                  onGroupBboxesChanged={handleGroupBboxesChanged}
                  onSelect={setFocusedId}
                  onUpdateDoc={updateDoc}
                  onContextMenu={(id, kind, e) => {
                    setStepCtx({ id, kind, x: e.clientX, y: e.clientY });
                  }}
                />
                {/* Floating action bar — appears when ≥2 step nodes are
                    selected. Lets the user create a group or add to one. */}
                <GroupActionBar
                  selectedNodeIds={selectedStepIds}
                  groups={docGroups}
                  onCreateGroup={handleCreateGroup}
                  onAddToGroup={handleAddToGroup}
                  onClearSelection={() => setSelectedStepIds([])}
                />
                {/* Phase A Layer 6 — toggle to Volume / Sankey view.
                    Top-right of the canvas; same place dbt Cloud and
                    Dagster put their view-mode controls. */}
                <button
                  type="button"
                  onClick={() => setCanvasMode("volume")}
                  className="absolute top-3 right-3 z-10 text-xs px-3 py-1.5 rounded-md border border-border bg-card/95 backdrop-blur shadow-sm hover:bg-muted transition-colors flex items-center gap-1.5"
                  title="Switch to Sankey volume view"
                >
                  <span aria-hidden>🌊</span>
                  Volume view
                </button>
                {/* The Sankey itself overlays the canvas when active.
                    Picks up the same column-trace state the canvas uses,
                    so hovering a column header in the live grid dims
                    off-lineage bands in the Sankey too. */}
                {canvasMode === "volume" && (
                  <SankeyView
                    doc={doc}
                    manifests={manifestsById}
                    nodeMetrics={nodeMetricsForCanvas}
                    tracedNodeIds={tracedNodeIds}
                    onClose={() => setCanvasMode("structure")}
                  />
                )}
              </div>
            )}
          </div>
          {/* Sticky floating Run for long pipelines — the toolbar Run is
              offscreen on small viewports once you have ~10 steps. */}
          {doc.nodes.length >= 8 && (
            <Button
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending || doc.nodes.length === 0}
              title="Run on backend"
              className="!bg-emerald-500 !text-emerald-950 hover:!bg-emerald-400 fixed bottom-6 right-[360px] z-20 shadow-lg"
            >
              {runMutation.isPending || runProgress.status === "queued" || runProgress.status === "running"
                ? "⏳ Running…"
                : "▶️ Run"}
            </Button>
          )}
        </section>

        {/* Right side panel */}
        <aside className="w-[340px] shrink-0 border-l border-border bg-background/40 backdrop-blur flex flex-col min-h-0">
          <div className="flex border-b border-border shrink-0">
            {(["params", "hints", "lineage"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={[
                  "flex-1 px-3 py-2 text-[11px] uppercase tracking-widest",
                  tab === t
                    ? "bg-card text-foreground border-b-2 border-foreground"
                    : "text-muted-foreground hover:bg-muted/40",
                ].join(" ")}
              >
                {t === "params" && "🎛 Params"}
                {t === "hints" && "💡 Hints"}
                {t === "lineage" && "🧬 Lineage"}
                {t === "hints" && suggestions.length > 0 && (
                  <span className="ml-1 text-[10px] text-foreground/70">{suggestions.length}</span>
                )}
              </button>
            ))}
          </div>
          <div className="p-4 overflow-y-auto flex-1">
            {tab === "params" && (
              selectedNode && selectedManifest ? (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                      Step
                      <HelpLink topic="Editing step parameters" anchor="4-the-editor--data-on-top-steps-on-bottom" />
                    </p>
                    <div className="flex items-center gap-1">
                      {/* OK = "I'm done editing this step, take me back to
                          the source data". For chart / forecast / Polars-only
                          steps the params panel is the only useful focus —
                          once configured, the user wants the grid back so
                          they can keep transforming. We pop focus to the
                          step's first upstream input (typically the dataset
                          or the previous step). The new step itself remains
                          in the pipeline; only the FOCUS moves. */}
                      <Button
                        size="xs"
                        variant="default"
                        onClick={() => {
                          const firstInput = Object.values(selectedNode.inputs ?? {})[0];
                          const upstream = firstInput?.ref;
                          if (upstream) {
                            setFocusedId(upstream);
                          } else {
                            // Orphan node (no inputs). Fall back to the
                            // first dataset, else clear focus.
                            setFocusedId(doc.datasets[0]?.id ?? null);
                          }
                        }}
                        title="Done editing this step — return to the upstream data"
                      >
                        ✓ OK
                      </Button>
                      <Button size="xs" variant="ghost" onClick={() => {
                        const next = removeNodeFromDoc(doc, selectedNode.id);
                        updateDoc(next);
                        const lastNode = next.nodes[next.nodes.length - 1];
                        setFocusedId(lastNode?.id ?? next.datasets[0]?.id ?? null);
                      }}>🗑 Delete</Button>
                    </div>
                  </div>
                  <h3 className="text-sm font-semibold mb-1">{selectedManifest.label}</h3>
                  <p className="text-[11px] text-muted-foreground mb-2">{selectedManifest.description}</p>
                  {selectedNode.step.startsWith("pipeline:") && (
                    <SubPipelinePinBadge
                      step={selectedNode.step}
                      pinnedEtag={Number(selectedNode.params?.pinnedEtag) || 1}
                      onUpgrade={(toEtag) => {
                        // Bump the pinnedEtag on this node's params so
                        // the next compile pulls the latest snapshot.
                        const next = setNodeParams(doc, selectedNode.id, {
                          ...selectedNode.params,
                          pinnedEtag: toEtag,
                        });
                        updateDoc(next);
                        toast.success(`🪆 Upgraded to v${toEtag}`);
                      }}
                    />
                  )}
                  {/* Auto-preview indicator — surfaces the editor's UX intent
                      (no Apply / Preview button; every change re-runs the
                      preview after a short debounce) so users don't go
                      hunting for one. The pulsing dot tracks `previewLoading`
                      from the parent — green dot when idle, amber pulse while
                      a fresh preview is in flight. */}
                  <div
                    className="flex items-center gap-1.5 mb-3 text-[10px] uppercase tracking-widest text-muted-foreground/80"
                    title="Every change re-runs the preview automatically. There's no separate Apply or Preview button."
                  >
                    <span
                      className={[
                        "inline-block size-1.5 rounded-full",
                        previewLoading
                          ? "bg-amber-400 animate-pulse"
                          : "bg-emerald-400",
                      ].join(" ")}
                      aria-hidden
                    />
                    <span>{previewLoading ? "Updating preview…" : "Auto-preview · live"}</span>
                  </div>
                  <ParamForm
                    // Keying on node id forces a full remount on node switch
                    // so child editors with self-initialized state (e.g. the
                    // FilterBuilder's parsed-once useMemo) don't leak stale
                    // state between nodes. P1 review fix.
                    key={selectedNode.id}
                    manifest={selectedManifest}
                    values={selectedNode.params}
                    upstreamColumns={upstreamColumns}
                    // Context for the bespoke join panel. Only `join`
                    // currently consumes these; other steps ignore them.
                    pipelineId={pipelineId}
                    etag={etag ?? 0}
                    inputRefs={Object.fromEntries(
                      Object.entries(selectedNode.inputs ?? {})
                        .map(([port, ref]) => [port, ref?.ref ?? null]),
                    )}
                    eligibleSources={eligibleSourcesFor(
                      doc,
                      selectedNode.id,
                      Object.fromEntries(
                        (datasetsQ.data ?? []).map((d) => [datasetRefId(d), d.name]),
                      ),
                    )}
                    onSetInputRef={(port, newRef) => {
                      const labelMap = Object.fromEntries(
                        (datasetsQ.data ?? []).map((d) => [datasetRefId(d), d.name]),
                      );
                      const r = rewireOrBranchInput(doc, selectedNode.id, port, newRef);
                      updateDoc(r.doc);
                      if (r.branched) {
                        setFocusedId(r.nodeId);
                        const sourceLabel =
                          eligibleSourcesFor(doc, selectedNode.id, labelMap).find((s) => s.id === newRef)?.label
                          ?? newRef;
                        toast.success(
                          `Branched mid-pipeline join · downstream chain preserved`,
                          { description: `New ${port} = ${sourceLabel}` },
                        );
                      }
                    }}
                    onSwapJoinSides={() => {
                      const r = swapJoinSides(doc, selectedNode.id);
                      updateDoc(r.doc);
                      if (r.branched) {
                        setFocusedId(r.nodeId);
                        toast.success(
                          `Branched mid-pipeline join · downstream chain preserved`,
                          { description: "Sides + keys + suffixes flipped" },
                        );
                      }
                    }}
                    onChange={(next) => updateDoc(setNodeParams(doc, selectedNode.id, next))}
                    // Show the 🪆 expose pill on each param. The toggle
                    // is always visible (not gated on publishedAsStep)
                    // so the user can prepare exposure declarations
                    // ahead of publishing. The published-step manifest
                    // generator only acts on these when the pipeline
                    // metadata.publishedAsStep is set.
                    exposedParams={
                      ((selectedNode.ui as { exposedParams?: Record<string, { alias: string; help?: string }> } | undefined)?.exposedParams) ?? undefined
                    }
                    onExposeParam={(paramKey, next) =>
                      updateDoc(setNodeExposedParam(doc, selectedNode.id, paramKey, next))
                    }
                  />
                  {/* Free-form note attached to the step. Persists in
                      node.ui.note so it travels with the pipeline document
                      (export / import / share-via-Git). Last-write-wins on
                      multi-session edits — same model as everything else
                      in the doc. No threading / authorship — that needs a
                      real CRDT layer we explicitly skip for now. */}
                  <div className="mt-4 pt-4 border-t border-border/40">
                    <label className="text-[11px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 mb-1.5">
                      <span>💬 Note</span>
                      <span className="text-[10px] normal-case tracking-normal text-muted-foreground/70">
                        (saved with pipeline)
                      </span>
                    </label>
                    <textarea
                      value={String(selectedNode.ui?.note ?? "")}
                      onChange={(e) => {
                        const next: PipelineDocument = {
                          ...doc,
                          nodes: doc.nodes.map((n) =>
                            n.id === selectedNode.id
                              ? { ...n, ui: { ...(n.ui ?? {}), note: e.target.value } }
                              : n,
                          ),
                        };
                        updateDoc(next);
                      }}
                      placeholder="Why this step exists, edge cases to watch, links to docs/issues…"
                      className="w-full text-xs rounded-md border border-input bg-background px-2 py-1.5 min-h-[60px]"
                    />
                  </div>
                </div>
              ) : (
                <div className="text-center text-xs text-muted-foreground pt-12">
                  <div className="text-3xl mb-2">👆</div>
                  Select a step in the strip below to edit it. The grid above shows that step's output.
                </div>
              )
            )}
            {tab === "hints" && (
              <>
                {/* AI cards apply to any focused node — every step's
                    output is itself a "current dataset". When focused
                    on a step, the AI works on the step's actual sampled
                    output (via metadata.sampling); applying a route
                    mid-chain branches off so the existing flow stays
                    intact. The card is opt-in (click-to-fetch) so the
                    LLM never fires on every panel open. */}
                {focusedId && (schemas[focusedId] || isFocusedDataset) && doc && (
                  (() => {
                    const focusedNode = doc.nodes.find((n) => n.id === focusedId);
                    const focusedManifest = focusedNode
                      ? manifestsById[focusedNode.step]
                      : undefined;
                    const focusedLabel = focusedNode
                      ? (focusedNode.ui?.label || focusedManifest?.label || focusedNode.step)
                      : (focusedDatasetReal?.name || "");
                    const willBranch = !!focusedNode && hasSuccessors(doc, focusedId);
                    // The AI route applier — picks insert vs branch
                    // automatically based on whether the focused node
                    // has downstream successors. Branching keeps the
                    // existing chain intact instead of silently
                    // re-wiring it through the new step.
                    const applyChain = (
                      routeSteps: ReadonlyArray<{
                        step_id: string;
                        params: Record<string, unknown>;
                        right_ref?: string | null;
                      }>,
                    ) => {
                      let cursor = focusedId;
                      let nextDoc = doc;
                      const byId: Record<string, StepManifest> = {};
                      for (const m of stepsQ.data ?? []) byId[m.id] = m;
                      const branchedAtStart = willBranch;
                      try {
                        for (let i = 0; i < routeSteps.length; i++) {
                          const s = routeSteps[i];
                          const m = byId[s.step_id];
                          if (!m) continue;
                          const params = { ...defaultParams(m), ...s.params };
                          // Only the FIRST step branches; subsequent
                          // steps continue linearly off it. Otherwise
                          // every step would fan out, producing a star
                          // instead of a chain.
                          const useBranch = branchedAtStart && i === 0;
                          const { doc: d2, nodeId } = useBranch
                            ? branchStepAfter(nextDoc, m, params, cursor!)
                            : insertStepAfter(nextDoc, m, params, cursor);
                          nextDoc = d2;
                          // Joins only get one input port wired by the
                          // generic insert (the `left` port pointing at
                          // the cursor / branched node). Wire the right
                          // port from the AI's `right_ref` hint when
                          // present + the ref exists in the doc.
                          if (
                            s.step_id === "join"
                            && typeof s.right_ref === "string"
                            && s.right_ref
                          ) {
                            const refId = s.right_ref;
                            const refExists =
                              nextDoc.datasets.some((d) => d.id === refId)
                              || nextDoc.nodes.some((n) => n.id === refId);
                            if (refExists) {
                              nextDoc = {
                                ...nextDoc,
                                nodes: nextDoc.nodes.map((n) =>
                                  n.id === nodeId
                                    ? {
                                        ...n,
                                        inputs: {
                                          ...n.inputs,
                                          right: { ref: refId },
                                        },
                                      }
                                    : n,
                                ),
                              };
                            }
                          }
                          cursor = nodeId;
                        }
                        updateDoc(nextDoc);
                        setFocusedId(cursor);
                        setTab("params");
                        toast.success(
                          branchedAtStart
                            ? `Branched ${routeSteps.length} step${routeSteps.length === 1 ? "" : "s"} off “${focusedLabel}”`
                            : `Added ${routeSteps.length} step${routeSteps.length === 1 ? "" : "s"}`,
                        );
                      } catch (e) {
                        toast.error((e as Error).message);
                      }
                    };
                    return (
                      <>
                        <ExplainDataset
                          nodeId={focusedId}
                          pipelineId={pipelineId}
                          nodeLabel={focusedNode ? focusedLabel : undefined}
                        />
                        <AiSuggestSteps
                          nodeId={focusedId}
                          pipelineId={pipelineId}
                          nodeLabel={focusedNode ? focusedLabel : undefined}
                          steps={stepsQ.data ?? []}
                          onApplyRoute={applyChain}
                        />
                        <AiVizHints
                          nodeId={focusedId}
                          pipelineId={pipelineId}
                          nodeLabel={focusedNode ? focusedLabel : undefined}
                          steps={stepsQ.data ?? []}
                          onApply={(manifest, params) =>
                            applyChain([{ step_id: manifest.id, params }])
                          }
                        />
                      </>
                    );
                  })()
                )}
                <SuggestionsPanel
                  suggestions={suggestions}
                  onApply={handleApplySuggestion}
                  onHover={setHoveredHintColumn}
                  loading={isFocusedDataset && datasetProfileQ.isLoading}
                />
              </>
            )}
            {tab === "lineage" && (
              <LineageView schemas={schemas} doc={doc} />
            )}
          </div>
        </aside>
      </div>

      {/* Run progress / output */}
      {(runProgress.status === "running" || runProgress.status === "queued") && (
        <div className="border-t border-border px-4 py-2 text-xs text-muted-foreground bg-muted/20 shrink-0">
          ⏳ {runProgress.stage ?? runProgress.status}…
        </div>
      )}
      {outputPage && (
        <BackendResultPanel page={outputPage} onClose={() => setOutputPage(null)} runId={run?.id ?? null} />
      )}
      {run?.artifacts && Object.keys(run.artifacts).length > 0 && (
        <ArtifactsPanel runId={run.id} artifacts={run.artifacts} />
      )}
      <SamplingDialog
        open={samplingOpen}
        value={
          ((doc.metadata?.sampling as SamplingConfig | undefined) ?? {
            method: "head",
            size: 100_000,
          })
        }
        // Columns from the first dataset's schema. Sampling applies
        // pipeline-wide; we surface the upstream-most schema so column
        // pickers show fields that exist before any step renames them.
        // Multi-dataset pipelines: this picks the first dataset's
        // columns — the user can switch datasets if they need a
        // different surface, or pick a step-output schema explicitly.
        availableColumns={(() => {
          const firstDs = doc.datasets[0];
          const schema = firstDs ? schemas[firstDs.id] : null;
          if (!schema) return [];
          return Object.entries(schema).map(([name, type]) => ({ name, type: String(type) }));
        })()}
        onChange={(next) => {
          const meta = { ...(doc.metadata ?? {}), sampling: next };
          updateDoc({ ...doc, metadata: meta });
          // Live-preview will re-key on the new etag → fresh sample.
        }}
        onClose={() => setSamplingOpen(false)}
      />

      <LabelPromptDialog
        open={saveDialogOpen}
        title="💾 Save checkpoint"
        lede="Optional label — helps you find this version later in run history."
        placeholder="e.g. before adding the rolling-window step"
        confirmLabel="💾 Save"
        onConfirm={(label) => onSaveExplicit(label)}
        onClose={() => setSaveDialogOpen(false)}
      />
      <LabelPromptDialog
        open={saveAsDialogOpen}
        title="📋 Save As — new pipeline"
        lede="Cloned with the current state. The new pipeline gets its own history, runs, and id."
        placeholder={`Copy of ${doc.name}`}
        defaultValue={`Copy of ${doc.name}`}
        confirmLabel="📋 Clone"
        required
        onConfirm={(name) => name && onSaveAs(name)}
        onClose={() => setSaveAsDialogOpen(false)}
      />

      <PublishAsStepDialog
        open={publishOpen}
        doc={doc}
        onClose={() => setPublishOpen(false)}
        onPublish={(cfg: PublishedAsStepConfig) => {
          // Updating metadata.publishedAsStep flips dirty → autosave
          // picks it up on the next debounce. We also force-flush via
          // a manual_save so the publication has its own labeled
          // checkpoint in history (helps when the consumer pins to a
          // specific version).
          updateDoc({
            ...doc,
            metadata: { ...(doc.metadata ?? {}), publishedAsStep: cfg },
          });
          setPublishOpen(false);
          toast.success(`🪆 Published as "${cfg.label}"`);
          queryClient.invalidateQueries({ queryKey: ["steps"] });
        }}
        onUnpublish={() => {
          const next = { ...doc, metadata: { ...(doc.metadata ?? {}) } } as typeof doc;
          delete (next.metadata as Record<string, unknown>).publishedAsStep;
          updateDoc(next);
          setPublishOpen(false);
          toast.success("🪆 Unpublished — consumers will see this disappear from their pickers.");
          queryClient.invalidateQueries({ queryKey: ["steps"] });
        }}
      />

      <PipelineDoctorDialog
        open={pendingDiagnoses.length > 0}
        pipelineId={pipelineId}
        diagnoses={pendingDiagnoses}
        onSkip={() => {
          // Dismiss every issue currently pending (fixable + unfixable
          // alike — the user has seen them, no point re-asking).
          recordDismissals(
            pipelineId,
            pendingDiagnoses.map((d) => d.id),
          );
          setPendingDiagnoses([]);
        }}
        onApply={(selected) => {
          if (!doc) return;
          const fixed = applyFixes(doc, selected);
          // Re-resolve `focusedId` if the active focus pointed at
          // something that just got renamed. Without this, applying a
          // dataset-rename fix would leave the focus pointing at the
          // old id → grid shows "No data" and the user thinks the fix
          // broke things. We match by URI for renamed datasets and by
          // ui-position for renamed nodes (the latter doesn't happen
          // today but keeps the logic future-proof).
          let nextFocus = focusedId;
          if (focusedId) {
            const stillExists =
              fixed.datasets.some((d) => d.id === focusedId) ||
              fixed.nodes.some((n) => n.id === focusedId);
            if (!stillExists) {
              const oldDs = doc.datasets.find((d) => d.id === focusedId);
              if (oldDs) {
                const newDs = fixed.datasets.find((d) => d.uri === oldDs.uri);
                if (newDs) nextFocus = newDs.id;
              }
              // Fallback: pick the first dataset so the editor doesn't
              // land on an empty focus state.
              if (nextFocus === focusedId) {
                nextFocus = fixed.datasets[0]?.id ?? null;
              }
            }
          }
          updateDoc(fixed);
          if (nextFocus !== focusedId) setFocusedId(nextFocus);
          // Dismiss everything we just resolved + any unfixable items
          // we showed alongside (the user saw them; don't re-ask).
          recordDismissals(
            pipelineId,
            pendingDiagnoses.map((d) => d.id),
          );
          setPendingDiagnoses([]);
          toast.success(
            `🩺 Applied ${selected.length} tune-up${selected.length === 1 ? "" : "s"} — Save to keep`,
            { duration: 5000 },
          );
        }}
      />

      <QuickAddMenu
        open={quickAdd !== null}
        onClose={() => setQuickAdd(null)}
        onPick={onPickStep}
        anchor={quickAdd}
        // Upstream schema = the focused node's outputs. When nothing is
        // focused (empty pipeline / first add), pass `{}` and the picker
        // skips greying — there's no schema to disqualify against.
        upstreamSchema={focusedId ? schemas[focusedId] : undefined}
        pipelineId={pipelineId}
        focusedNodeId={focusedId}
      />

      {stepCtx && (
        <StepContextMenu
          ctx={stepCtx}
          onClose={() => setStepCtx(null)}
          onAction={(act) => {
            const id = stepCtx.id;
            setStepCtx(null);
            if (act === "edit") {
              setFocusedId(id);
              setTab("params");
            } else if (act === "duplicate") {
              const node = doc.nodes.find((n) => n.id === id);
              if (!node) return;
              const newId = `n_${Date.now().toString(36)}${Math.floor(Math.random() * 0xffff).toString(36)}`;
              const dupNode = { ...node, id: newId, ui: { ...(node.ui ?? {}), x: (node.ui?.x ?? 200) + 30, y: (node.ui?.y ?? 100) + 20 } };
              // Append at end (linear) — wired from current terminal.
              const lastNode = doc.nodes[doc.nodes.length - 1];
              const lastRef = lastNode
                ? { ref: lastNode.id, port: lastNode.outputs[0] ?? "out" }
                : doc.datasets[0] ? { ref: doc.datasets[0].id } : null;
              if (!lastRef) return;
              dupNode.inputs = { in: lastRef };
              updateDoc({ ...doc, nodes: [...doc.nodes, dupNode] });
              setFocusedId(newId);
              toast.success(`Duplicated`);
            } else if (act === "delete") {
              const next = removeNodeFromDoc(doc, id);
              updateDoc(next);
              if (focusedId === id) {
                const lastNode = next.nodes[next.nodes.length - 1];
                setFocusedId(lastNode?.id ?? next.datasets[0]?.id ?? null);
              }
            } else if (act === "insert_after") {
              setFocusedId(id);
              // Open the quick-add menu near the strip
              setQuickAdd({
                x: stepCtx.x,
                y: stepCtx.y,
                w: 200,
                h: 28,
              });
            }
          }}
        />
      )}

      {/* Editor tour — only opens when the user clicks the 🧭 toolbar button.
          Auto-firing was removed because the fixed-inset overlay swallowed
          clicks on the Add-dataset dropdown. */}
      <EditorTour open={editorTourOpen} onClose={() => setEditorTourOpen(false)} />

      {columnDNA && (
        <ColumnDNAView
          pipelineId={pipelineId}
          nodeId={columnDNA.nodeId}
          column={columnDNA.column}
          onClose={() => setColumnDNA(null)}
        />
      )}

      <LineagePanel
        open={lineagePanel !== null}
        pipelineId={pipelineId}
        nodeId={lineagePanel?.nodeId ?? null}
        column={lineagePanel?.column ?? null}
        onClose={() => setLineagePanel(null)}
        onJumpToNode={(nid) => {
          setFocusedId(nid);
          setLineagePanel(null);
        }}
      />

      <SqlView
        pipelineId={pipelineId}
        open={sqlViewOpen}
        onClose={() => setSqlViewOpen(false)}
        terminal={focusedId}
      />

      {/* Phase A Layer 4 — group edit popover. Position-fixed so it
          renders correctly regardless of where the page is scrolled. */}
      {editingGroup && (
        (() => {
          const g = docGroups.find((x) => x.id === editingGroup.id);
          if (!g) {
            // Group was deleted; clear stale state.
            setTimeout(() => setEditingGroup(null), 0);
            return null;
          }
          return (
            <GroupEditPopover
              group={g}
              anchor={editingGroup.anchor}
              onSave={handleSaveGroup}
              onDelete={() => handleDeleteGroup(g.id)}
              onClose={() => setEditingGroup(null)}
            />
          );
        })()
      )}
    </main>
  );
}

const EDITOR_TOUR_STEPS: TourStep[] = [
  {
    title: "🛤 The pipeline strip",
    body: (
      <>
        Every step you add appears here at the bottom. Click a pill to focus
        that step — the grid above shows its output.
      </>
    ),
    target: '[data-tour="editor-strip"]',
    placement: "top",
  },
  {
    title: "📊 Live grid above",
    body: (
      <>
        The grid mirrors the focused step's output, recomputed in your browser
        on a sample. Hover any column to highlight it. Click <strong>⋯</strong>
        on a column header for quick actions (filter, cast, rename, …).
      </>
    ),
    placement: "bottom",
  },
  {
    title: "▶ Run on backend",
    body: (
      <>
        When you're happy with the preview, click here to run the full pipeline
        on the backend over the whole dataset. Outputs land as Parquet and any
        configured charts/files appear in the artifacts panel.
      </>
    ),
    target: '[data-tour="editor-run"]',
    placement: "bottom",
    nextLabel: "Got it",
  },
];

/**
 * Editor tour. Previously auto-fired after 800ms on every visit, which
 * caused a fixed-inset SVG backdrop to swallow clicks (notably on the
 * Add dataset dropdown — the user couldn't pick a dataset). Auto-firing a
 * full-viewport overlay is bad UX even without the click conflict: people
 * land on a fresh pipeline and want to *do* something, not be tutorialized.
 *
 * The tour now only fires when the user explicitly clicks the 🧭 Tour
 * button in the toolbar (parent `Editor` controls the open state).
 */
export function EditorTour({
  open, onClose,
}: { open: boolean; onClose: () => void }) {
  return (
    <Tour
      open={open}
      onClose={onClose}
      steps={EDITOR_TOUR_STEPS}
      storageKey="dig.tour.editor.v1"
    />
  );
}

function StepContextMenu({
  ctx, onClose, onAction,
}: {
  ctx: { id: string; kind: "node" | "dataset"; x: number; y: number };
  onClose: () => void;
  onAction: (a: "edit" | "duplicate" | "insert_after" | "delete") => void;
}) {
  const items =
    ctx.kind === "node"
      ? [
          { id: "edit" as const, label: "🎛 Edit params" },
          { id: "duplicate" as const, label: "📑 Duplicate" },
          { id: "insert_after" as const, label: "➕ Insert step after" },
          { id: "delete" as const, label: "🗑 Delete" },
        ]
      : [
          { id: "edit" as const, label: "📋 Show in grid" },
          { id: "delete" as const, label: "🗑 Remove from pipeline" },
        ];
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    const onClick = () => onClose();
    window.addEventListener("keydown", onKey);
    setTimeout(() => window.addEventListener("click", onClick, { once: true }), 0);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const w = 200;
  const x = Math.min(ctx.x, window.innerWidth - w - 8);
  const y = Math.max(8, Math.min(ctx.y, window.innerHeight - 200));
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ type: "spring", stiffness: 360, damping: 28 }}
      style={{ position: "fixed", left: x, top: y, width: w }}
      className="z-50 rounded-lg border border-border bg-popover text-popover-foreground shadow-2xl py-1 text-sm"
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((it) => (
        <button
          key={it.id}
          type="button"
          onClick={() => onAction(it.id)}
          className="w-full text-left px-3 py-1.5 hover:bg-muted/60 transition-colors"
        >
          {it.label}
        </button>
      ))}
    </motion.div>
  );
}

// Minimal lineage view (per-node schemas).
function LineageView({
  schemas, doc,
}: {
  schemas: Record<string, Record<string, string>>;
  doc: PipelineDocument;
}) {
  const TYPE_EMOJI: Record<string, string> = {
    integer: "🔢", double: "🔢", string: "🅰️", date: "📅",
    datetime: "📅", boolean: "☑️", nested: "🧱", unknown: "❔",
  };
  const order: string[] = [
    ...doc.datasets.map((d) => d.id),
    ...doc.nodes.map((n) => n.id),
  ].filter((id) => schemas[id] && Object.keys(schemas[id]).length > 0);
  if (order.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Add a dataset and a step to see inferred schemas.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {order.map((nid) => (
        <div key={nid} className="rounded-lg border border-border bg-card/40 p-2">
          <p className="text-xs font-medium mb-1 truncate">
            <span className="text-muted-foreground/70">›</span> {nid}
          </p>
          <ul className="space-y-0.5">
            {Object.entries(schemas[nid]).map(([col, t]) => (
              <li key={col} className="text-[11px] flex items-center gap-1.5">
                <span aria-hidden>{TYPE_EMOJI[t] ?? "❔"}</span>
                <span className="truncate flex-1">{col}</span>
                <span className="text-muted-foreground text-[10px]">{t}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function BackendResultPanel({
  page, onClose, runId,
}: { page: RunOutputPage; onClose: () => void; runId?: string | null }) {
  // Lineage drawer state — clicking the 🔍 button on a row opens it.
  // runId is optional (some callers may show output without a run, e.g.
  // imported run records); when missing we hide the lineage button.
  const [traceRow, setTraceRow] = useState<number | null>(null);

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="border-t border-border bg-card/60 max-h-[260px] overflow-auto shrink-0"
    >
      <header className="sticky top-0 bg-background/80 backdrop-blur px-4 py-2 border-b border-border flex items-center gap-3 z-10">
        <span className="text-base">✅</span>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">
          Backend run result
        </p>
        <span className="text-xs text-muted-foreground tabular-nums">
          {fmtInt(page.totalRows)} rows · {page.columns.length} cols
        </span>
        {runId && (
          <span className="text-[10px] text-muted-foreground italic">
            click 🔍 on a row to trace its lineage
          </span>
        )}
        <span className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          ✕ Dismiss
        </button>
      </header>
      <div className="overflow-auto">
        <table className="text-xs tabular-nums">
          <thead>
            <tr>
              {runId && (
                <th className="px-2 py-1 border-b border-border w-8" aria-label="Lineage" />
              )}
              {page.columns.map((c) => (
                <th key={c.name} className="px-2 py-1 text-left font-medium border-b border-border whitespace-nowrap">
                  {c.name}{" "}
                  <span className="text-[10px] text-muted-foreground">{c.type.split("(")[0].toLowerCase()}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.rows.map((r, i) => (
              <tr key={i} className="hover:bg-muted/30 group">
                {runId && (
                  <td className="px-1 border-b border-border/30 align-middle">
                    <button
                      type="button"
                      onClick={() => setTraceRow(page.offset + i)}
                      title={`Trace lineage for row ${page.offset + i}`}
                      className="opacity-0 group-hover:opacity-100 transition-opacity hover:bg-muted rounded px-1 py-0.5 text-xs"
                    >
                      🔍
                    </button>
                  </td>
                )}
                {page.columns.map((c) => (
                  <td key={c.name} className="px-2 py-1 border-b border-border/30 whitespace-nowrap">
                    {String(r[c.name] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {runId && (
        <LineageDrawer
          open={traceRow !== null}
          onClose={() => setTraceRow(null)}
          runId={runId}
          rowIndex={traceRow}
        />
      )}
    </motion.section>
  );
}

// Reasonable default param values per built-in step.
function defaultParams(manifest: StepManifest): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(manifest.params)) {
    if (spec.default !== undefined) out[name] = spec.default;
    else if (spec.type === "boolean") out[name] = false;
    else if (spec.type === "array") out[name] = [];
    else if (spec.type === "object") out[name] = {};
  }
  return out;
}

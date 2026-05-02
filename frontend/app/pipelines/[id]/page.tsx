"use client";

import Link from "next/link";
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
import { usePersistedState } from "@/lib/use-persisted-state";
import { Tour, type TourStep } from "@/components/tour/tour";
import { Button, buttonVariants } from "@/components/ui/button";
import { LiveGrid } from "@/components/grid/live-grid";
import { GraphCanvas } from "@/components/canvas/graph-canvas";
import { PipelineStrip } from "@/components/canvas/pipeline-strip";
import { QuickAddMenu } from "@/components/canvas/quick-add-menu";
import { ExportMenu } from "@/components/canvas/export-menu";
import { ParamForm } from "@/components/canvas/param-form";
import { SaveIndicator } from "@/components/canvas/save-indicator";
import { SuggestionsPanel } from "@/components/canvas/suggestions-panel";
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

/** Append a linear single-input step to the end of a doc, wired from the current terminal. */
function appendLinearStep(
  doc: PipelineDocument,
  manifest: StepManifest,
  params: Record<string, unknown>,
): { doc: PipelineDocument; nodeId: string } {
  const lastNode = doc.nodes[doc.nodes.length - 1];
  const lastRef = lastNode
    ? { ref: lastNode.id, port: lastNode.outputs[0] ?? "out" }
    : doc.datasets[0]
      ? { ref: doc.datasets[0].id }
      : null;
  if (!lastRef) {
    throw new Error("Add a dataset before adding steps.");
  }
  const portsIn = manifest.io.inputs.ports ?? ["in"];
  const portsOut = manifest.io.outputs.ports ?? ["out"];
  const id = newNodeId();
  const node: PipelineNode = {
    id,
    step: manifest.id,
    stepVersion: manifest.version,
    inputs: { [portsIn[0]]: lastRef },
    outputs: portsOut,
    params,
    ui: {
      x: 220 + doc.nodes.length * 220,
      y: 100,
      label: manifest.label,
    },
  };
  return { doc: { ...doc, nodes: [...doc.nodes, node] }, nodeId: id };
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

  // Tour-of-pipeline
  const undoStack = useRef<PipelineDocument[]>([]);
  const redoStack = useRef<PipelineDocument[]>([]);
  const lastSnapshot = useRef<string>("");

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

  // Editor tour open state. Manually triggered via the 🧭 toolbar button —
  // auto-firing was removed because the tour overlay swallowed clicks on
  // the Add-dataset dropdown.
  const [editorTourOpen, setEditorTourOpen] = useState(false);

  useEffect(() => {
    if (pipeline.data) {
      const seed =
        Object.keys(pipeline.data.document).length === 0
          ? emptyDoc(pipelineId, "Untitled")
          : (pipeline.data.document as unknown as PipelineDocument);
      setDoc(seed);
      setEtag(pipeline.data.etag);
      setDirty(false);
      undoStack.current = [];
      redoStack.current = [];
      lastSnapshot.current = JSON.stringify(seed);
      // Default focus = last node, else the dataset
      const lastNode = seed.nodes[seed.nodes.length - 1];
      setFocusedId(lastNode?.id ?? seed.datasets[0]?.id ?? null);
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
      }
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [undo, redo]);

  // ---- Save (debounced) ----
  const saveMutation = useMutation({
    mutationFn: async (next: PipelineDocument) => {
      if (etag == null) throw new Error("etag unset");
      return api.updatePipeline(pipelineId, next, etag);
    },
    onSuccess: (resp) => {
      setEtag(resp.etag);
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ["pipelines"] });
    },
    onError: (e: Error) => toast.error(`Save failed: ${e.message}`),
  });
  useEffect(() => {
    if (!doc || !dirty) return;
    const t = setTimeout(() => saveMutation.mutate(doc), 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, dirty]);

  // ---- Validation / schema inference (server-side) ----
  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.validatePipeline(pipelineId);
        if (cancelled) return;
        setSchemas(res.schemas ?? {});
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

  const isFocusedDataset = useMemo(() => {
    if (!doc || !focusedId) return false;
    return doc.datasets.some((d) => d.id === focusedId);
  }, [doc, focusedId]);

  // Fetch raw rows when focused on a dataset (uses the DIG dataset id mapped from internal alias)
  const focusedDatasetReal = useMemo(() => {
    if (!doc || !focusedId || !datasetsQ.data) return null;
    const ds = doc.datasets.find((d) => d.id === focusedId);
    if (!ds) return null;
    return datasetsQ.data.find((d) => datasetRefId(d) === focusedId) ?? null;
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
    const t = setTimeout(async () => {
      try {
        const res = await previewPipeline(pipelineId, {
          terminal: focusedId,
          sampleRows: 100_000,
          previewLimit: 500,
          signal: ac.signal,
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
  }, [doc, focusedId, isFocusedDataset, pipelineId, etag]);

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
      return {
        columns: preview.columns,
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
    (manifest: StepManifest) => {
      if (!doc) return;
      try {
        const { doc: next, nodeId } = appendLinearStep(doc, manifest, defaultParams(manifest));
        updateDoc(next);
        setFocusedId(nodeId);
        setTab("params");
        toast.success(`Added ${manifest.label}`);
      } catch (e) {
        toast.error((e as Error).message);
      }
      setQuickAdd(null);
    },
    [doc, updateDoc],
  );

  // ---- Column actions: turn a column action into a pipeline step ----
  const currentSchema = useMemo(() => {
    if (!doc || !focusedId) return [];
    return Object.keys(schemas[focusedId] ?? {});
  }, [doc, focusedId, schemas]);

  const handleColumnAction = useCallback(
    (a: ColumnAction) => {
      if (!doc) return;
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
        }
      })();
      try {
        const prevDoc = doc;
        const { doc: next, nodeId } = appendLinearStep(doc, manifest, params);
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

  if (!doc) {
    return (
      <main id="main" className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        ⏳ Loading pipeline…
      </main>
    );
  }

  return (
    <main className="flex flex-1 flex-col h-screen min-h-0">
      {/* Top bar */}
      <header className="border-b border-border bg-background/80 backdrop-blur px-4 py-2 flex items-center gap-3 shrink-0">
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

        <Button size="sm" variant="ghost" onClick={undo} disabled={undoStack.current.length === 0} title="Undo (⌘Z)">
          ↩️
        </Button>
        <Button size="sm" variant="ghost" onClick={redo} disabled={redoStack.current.length === 0} title="Redo (⌘⇧Z)">
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
          <div className="flex-1 min-h-0">
            <LiveGrid
              columns={gridData.columns}
              rows={gridData.rows}
              totalRows={gridData.totalRows}
              sampleRows={preview?.sampleRows ?? 100_000}
              loading={gridData.loading}
              elapsedMs={gridData.elapsedMs}
              onColumnAction={handleColumnAction}
              onCellQuickFilter={handleCellQuickFilter}
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
                ) : previewError ? (
                  <div className="max-w-sm">
                    <div className="text-5xl mb-2">⚠️</div>
                    <p className="text-destructive">{previewError}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Adjust the focused step's params or undo to recover.
                    </p>
                  </div>
                ) : undefined
              }
            />
          </div>
          <div data-tour="editor-strip" className={canvasView === "graph" ? "h-[300px]" : ""}>
            {canvasView === "strip" ? (
              <PipelineStrip
                doc={doc}
                manifests={manifestsById}
                selectedId={focusedId}
                rowCounts={rowCounts}
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
              <GraphCanvas
                doc={doc}
                manifests={manifestsById}
                selectedId={focusedId}
                rowCounts={rowCounts}
                onSelect={setFocusedId}
                onUpdateDoc={updateDoc}
                onContextMenu={(id, kind, e) => {
                  setStepCtx({ id, kind, x: e.clientX, y: e.clientY });
                }}
              />
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
                    <Button size="xs" variant="ghost" onClick={() => {
                      const next = removeNodeFromDoc(doc, selectedNode.id);
                      updateDoc(next);
                      const lastNode = next.nodes[next.nodes.length - 1];
                      setFocusedId(lastNode?.id ?? next.datasets[0]?.id ?? null);
                    }}>🗑 Delete</Button>
                  </div>
                  <h3 className="text-sm font-semibold mb-1">{selectedManifest.label}</h3>
                  <p className="text-[11px] text-muted-foreground mb-3">{selectedManifest.description}</p>
                  <ParamForm
                    // Keying on node id forces a full remount on node switch
                    // so child editors with self-initialized state (e.g. the
                    // FilterBuilder's parsed-once useMemo) don't leak stale
                    // state between nodes. P1 review fix.
                    key={selectedNode.id}
                    manifest={selectedManifest}
                    values={selectedNode.params}
                    upstreamColumns={upstreamColumns}
                    onChange={(next) => updateDoc(setNodeParams(doc, selectedNode.id, next))}
                  />
                </div>
              ) : (
                <div className="text-center text-xs text-muted-foreground pt-12">
                  <div className="text-3xl mb-2">👆</div>
                  Select a step in the strip below to edit it. The grid above shows that step's output.
                </div>
              )
            )}
            {tab === "hints" && (
              <SuggestionsPanel
                suggestions={suggestions}
                onApply={handleApplySuggestion}
                onHover={setHoveredHintColumn}
                loading={isFocusedDataset && datasetProfileQ.isLoading}
              />
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
        <BackendResultPanel page={outputPage} onClose={() => setOutputPage(null)} />
      )}
      {run?.artifacts && Object.keys(run.artifacts).length > 0 && (
        <ArtifactsPanel runId={run.id} artifacts={run.artifacts} />
      )}

      <QuickAddMenu
        open={quickAdd !== null}
        onClose={() => setQuickAdd(null)}
        onPick={onPickStep}
        anchor={quickAdd}
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
  page, onClose,
}: { page: RunOutputPage; onClose: () => void }) {
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
              <tr key={i} className="hover:bg-muted/30">
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

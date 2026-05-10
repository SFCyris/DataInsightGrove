"use client";

/**
 * Phase A Layer 6 — Sankey volume view.
 *
 * A parallel view to the structural xyflow canvas: shows where data
 * volume reshapes through every step. Width encodes row count; color
 * encodes operation type. Filters shed visibly, joins multiply,
 * aggregates collapse.
 *
 * Reads the SAME data the canvas reads — the pipeline document for
 * structure + the latest run's nodeMetrics for row counts. No new
 * backend endpoint needed; the data plumbing piggybacks on the freshness/
 * run-state work.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { sankey, sankeyLeft, sankeyLinkHorizontal } from "d3-sankey";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior } from "d3-zoom";
import { motion, AnimatePresence } from "motion/react";
import { toast } from "sonner";

import { api } from "@/lib/api/client";
import type {
  PipelineDocument,
  StepManifest,
} from "@/lib/api/client";
import type { NodeRunMetrics } from "@/components/canvas/graph-canvas";
import { useURLState, buildShareLink } from "@/lib/use-url-state";

// ---- operation classification ------------------------------------------

type OpKind =
  | "source" | "filter" | "join" | "aggregate" | "derive"
  | "passthrough" | "sink";

// Tier 2 polish: flow alphas raised from 0.30-0.35 → 0.55-0.60 so
// bands feel like real "rivers of data," not pastel watercolour. The
// jump is subtle on light bands (passthrough) and dramatic on the
// chromatic ones (filter, join, derive) — matching how Flourish and
// Total Sankey present flows.
const OP_COLORS: Record<OpKind, { fill: string; flow: string; label: string; emoji: string }> = {
  source:      { fill: "rgb(82 82 91)",  flow: "rgba(82, 82, 91, 0.55)",  label: "Source",      emoji: "📥" },
  filter:      { fill: "rgb(244 63 94)", flow: "rgba(244, 63, 94, 0.55)", label: "Filter",      emoji: "🔍" },
  join:        { fill: "rgb(139 92 246)",flow: "rgba(139, 92, 246, 0.55)",label: "Join",        emoji: "🔗" },
  aggregate:   { fill: "rgb(245 158 11)",flow: "rgba(245, 158, 11, 0.55)",label: "Aggregate",   emoji: "🧮" },
  derive:      { fill: "rgb(16 185 129)",flow: "rgba(16, 185, 129, 0.55)",label: "Derive",      emoji: "➕" },
  passthrough: { fill: "rgb(161 161 170)",flow:"rgba(161, 161, 170, 0.45)",label:"Passthrough", emoji: "⏭" },
  sink:        { fill: "rgb(82 82 91)",  flow: "rgba(82, 82, 91, 0.55)",  label: "Sink",        emoji: "📤" },
};

/** Classify a step into a Sankey op color. Maps from step manifest's
 *  category — the 9 DIG categories collapse into 7 op kinds. */
function opKindForStep(stepId: string, manifest: StepManifest | undefined): OpKind {
  if (!manifest) return "passthrough";
  const cat = manifest.category;
  // Specific step ids that span multiple categories
  if (stepId === "join") return "join";
  if (stepId === "filter_rows" || stepId === "filter") return "filter";
  if (stepId === "group_aggregate" || stepId === "aggregate") return "aggregate";
  if (stepId === "derive_column" || stepId === "derive") return "derive";
  // Categories
  if (cat === "ingest") return "source";
  // `visualize` (charts, plots) and `output` (file writes) are both
  // terminal mirrors of upstream data — they belong in the same "sink"
  // bucket so the toolbar's "Show output sinks" toggle hides both.
  if (cat === "output" || cat === "visualize") return "sink";
  if (cat === "shape" || cat === "clean") return "passthrough";
  if (cat === "derive") return "derive";
  if (cat === "combine") return "join";
  if (cat === "aggregate") return "aggregate";
  return "passthrough";
}

// ---- types -------------------------------------------------------------

interface SankeyNodeIn {
  id: string;
  label: string;
  op: OpKind;
  rows: number | null;
  // for the legend / drill panel
  emoji?: string;
  isDataset?: boolean;
}
interface SankeyLinkIn {
  source: string;
  target: string;
  value: number;
  op: OpKind;        // color of the band — based on the TARGET op
}

// d3-sankey augments the inputs with x0, y0, x1, y1, etc. We re-type them.
type SankeyNodeOut = SankeyNodeIn & {
  x0: number; x1: number; y0: number; y1: number;
  index: number;
};
type SankeyLinkOut = {
  source: SankeyNodeOut;
  target: SankeyNodeOut;
  value: number;
  op: OpKind;
  width: number;
  y0: number;
  y1: number;
};

interface Props {
  doc: PipelineDocument;
  manifests: Record<string, StepManifest>;
  nodeMetrics?: Record<string, NodeRunMetrics>;
  width?: number;
  /** Hard floor on height. The actual rendered height grows from here
   *  based on the number of nodes per column so bands don't overlap. */
  height?: number;
  /** Phase A Layer 3 link: when the user is hovering a column header in
   *  the live grid, this carries the set of canvas node IDs that
   *  contribute to that column. The Sankey dims off-lineage bands /
   *  nodes to match. */
  tracedNodeIds?: Set<string> | null;
  onClose: () => void;
}

// Image-export / file-output sinks add no information to a volume view —
// they're terminal mirrors of upstream data. Filtered out by default in
// `buildSankey` so the layout has more breathing room. Toggle restores
// them if a user wants to see "where does this data ultimately land".

// ---- main component ----------------------------------------------------

export function SankeyView({
  doc, manifests, nodeMetrics, width = 1400, height = 560,
  tracedNodeIds, onClose,
}: Props) {
  // Phase-A-pro #2 — URL-encoded interactive state. One blob per
  // surface under `?sk=` so the user can refresh / share / bookmark
  // any drilled-in view. Set is encoded as an array; no extra
  // wrapping needed.
  type SankeyURLState = {
    drill: string | null;
    showSinks: boolean;
    kinds: OpKind[];
    compareMode: boolean;
  };
  const SANKEY_DEFAULT: SankeyURLState = {
    drill: null,
    showSinks: false,
    kinds: [],
    compareMode: false,
  };
  const [skState, setSkState] = useURLState<SankeyURLState>("sk", SANKEY_DEFAULT);
  const drill = skState.drill;
  const setDrill = (v: string | null | ((p: string | null) => string | null)) =>
    setSkState((p) => ({ ...p, drill: typeof v === "function" ? v(p.drill) : v }));
  const showSinks = skState.showSinks;
  const setShowSinks = (v: boolean) => setSkState((p) => ({ ...p, showSinks: v }));
  const compareMode = skState.compareMode;
  const setCompareMode = (v: boolean | ((p: boolean) => boolean)) =>
    setSkState((p) => ({ ...p, compareMode: typeof v === "function" ? v(p.compareMode) : v }));
  // activeKinds derived from URL state. Set ↔ Array round-trip.
  const activeKinds = useMemo(() => new Set<OpKind>(skState.kinds), [skState.kinds]);
  const setActiveKinds = (
    updater: Set<OpKind> | ((prev: Set<OpKind>) => Set<OpKind>),
  ) =>
    setSkState((p) => {
      const cur = new Set<OpKind>(p.kinds);
      const next = typeof updater === "function" ? updater(cur) : updater;
      return { ...p, kinds: Array.from(next) };
    });
  const [hoverLink, setHoverLink] = useState<
    { idx: number; x: number; y: number } | null
  >(null);
  const [previousMetrics, setPreviousMetrics] = useState<Record<string, NodeRunMetrics> | null>(null);
  // Tier 3: annotation pins — ephemeral, session-scoped notes the user
  // can drop on bands. Persisted in localStorage keyed by pipeline id
  // so notes survive a page refresh without polluting the saved doc.
  const [annotations, setAnnotations] = useState<Record<string, string>>({});
  const [annotateMode, setAnnotateMode] = useState(false);
  // Tier-pro zoom+pan: scroll-wheel zoom 0.5×–5×, drag pan, double-
  // click reset. Powered by d3-zoom on the SVG with the transform
  // applied to a single inner <g> wrapping every visible element.
  const [zoomScale, setZoomScale] = useState(1);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const zoomGroupRef = useRef<SVGGElement | null>(null);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  // Load annotations from localStorage on mount.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(`dig:sankey-annotations:${doc.id ?? "anon"}`);
      if (raw) setAnnotations(JSON.parse(raw));
    } catch {
      // localStorage unavailable / corrupt — ignore, no notes is a fine default.
    }
  }, [doc.id]);

  // Persist annotations on change.
  useEffect(() => {
    try {
      localStorage.setItem(
        `dig:sankey-annotations:${doc.id ?? "anon"}`,
        JSON.stringify(annotations),
      );
    } catch {
      // Ignore storage quota / privacy mode errors — annotations stay
      // in memory and reset on reload.
    }
  }, [annotations, doc.id]);

  // When compareMode flips ON, fetch the prior succeeded run's metrics.
  // We use the *second* most recent run (the latest is what we already
  // render) so the delta is "this run vs last run." Skip the fetch if
  // we don't have a pipeline id (shouldn't happen in normal flow).
  useEffect(() => {
    if (!compareMode || !doc.id) {
      setPreviousMetrics(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const runs = await api.listRuns(doc.id!);
        const succeeded = runs.filter((r) => r.status === "succeeded");
        if (succeeded.length < 2) {
          if (!cancelled) {
            toast.info("No previous run to compare against");
            setCompareMode(false);
          }
          return;
        }
        // succeeded[0] is the latest (already shown); [1] is the prior.
        const prior = succeeded[1];
        const detail = await api.getRun(prior.id);
        if (!cancelled) {
          setPreviousMetrics((detail.nodeMetrics ?? {}) as unknown as Record<string, NodeRunMetrics>);
        }
      } catch (e) {
        if (!cancelled) {
          toast.error(`Compare failed: ${(e as Error).message}`);
          setCompareMode(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [compareMode, doc.id]);

  const { nodes, links, layout } = useMemo(
    () => buildSankey(doc, manifests, nodeMetrics, width, height, showSinks),
    [doc, manifests, nodeMetrics, width, height, showSinks],
  );

  // Click-to-isolate: when a node is "drilled," compute the full
  // upstream + downstream reachability from that node. Anything outside
  // that chain dims to ~10% so the user sees just the data path the
  // clicked node participates in. This matches the path-isolation UX
  // in Flourish / Total Sankey / ECharts.
  const drillPath = useMemo<Set<string> | null>(() => {
    if (!drill) return null;
    // Round-3 QA finding: a stale ?sk= URL (e.g. an old shared link
    // pointing at a node that no longer exists in the current pipeline)
    // would create a one-element set with no neighbours, which dim
    // logic interprets as "the entire canvas is off-path". Without a
    // way to clear the drill, the user sees a uniformly dimmed Sankey
    // with no obvious next step. Detect the stale case here and act
    // as if no drill was set.
    const drillExists = links.some(
      (l) => l.source.id === drill || l.target.id === drill,
    );
    if (!drillExists) return null;
    const set = new Set<string>([drill]);
    // Reverse-walk upstream until closure stabilises.
    let changed = true;
    while (changed) {
      changed = false;
      for (const l of links) {
        if (set.has(l.target.id) && !set.has(l.source.id)) {
          set.add(l.source.id);
          changed = true;
        }
      }
    }
    // Forward-walk downstream.
    changed = true;
    while (changed) {
      changed = false;
      for (const l of links) {
        if (set.has(l.source.id) && !set.has(l.target.id)) {
          set.add(l.target.id);
          changed = true;
        }
      }
    }
    return set;
  }, [drill, links]);

  // Self-heal stale URL state: if the URL has a drill id that doesn't
  // match any node in the current Sankey, clear it from the URL so the
  // user lands on the default view (and a re-share doesn't reproduce
  // the stuck-canvas state).
  useEffect(() => {
    if (!drill) return;
    const exists = links.some((l) => l.source.id === drill || l.target.id === drill);
    if (!exists) {
      setDrill(null);
    }
  }, [drill, links, setDrill]);

  // Per-source total used to compute "% of source" in the band tooltip.
  const sourceOutTotals = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const l of links) {
      totals[l.source.id] = (totals[l.source.id] ?? 0) + l.value;
    }
    return totals;
  }, [links]);

  // Tier 3 dim policy: drill (path isolation) wins; then legend filter
  // (only show selected kinds); then external column trace from grid
  // hover. Each predicate works on a node-id, with band dim logic that
  // ANDs the two endpoint nodes.
  const isNodeDim = (id: string, op: OpKind): boolean => {
    if (drillPath) return !drillPath.has(id);
    if (activeKinds.size > 0 && !activeKinds.has(op)) return true;
    if (tracedNodeIds != null && !isOnTrace(id)) return true;
    return false;
  };
  const isLinkDim = (l: SankeyLinkOut): boolean => {
    if (drillPath) return !(drillPath.has(l.source.id) && drillPath.has(l.target.id));
    if (activeKinds.size > 0 && !activeKinds.has(l.source.op) && !activeKinds.has(l.target.op)) return true;
    if (tracedNodeIds != null && (!isOnTrace(l.source.id) || !isOnTrace(l.target.id))) return true;
    return false;
  };

  const toggleKindFilter = (kind: OpKind) => {
    setActiveKinds((cur) => {
      const next = new Set(cur);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

  const handleAnnotate = (bandKey: string) => {
    const existing = annotations[bandKey] ?? "";
    const next = window.prompt(
      existing ? "Edit annotation (clear to remove):" : "Add annotation:",
      existing,
    );
    if (next === null) return;
    setAnnotations((cur) => {
      const copy = { ...cur };
      if (next.trim() === "") delete copy[bandKey];
      else copy[bandKey] = next.trim();
      return copy;
    });
  };

  const linkKey = (l: SankeyLinkOut): string => `${l.source.id}->${l.target.id}`;

  // Bind d3-zoom to the SVG. Filter out interactions on band paths so
  // hover-tooltip + click-to-isolate keep working as primary actions —
  // panning fires only when the user drags on EMPTY canvas. Wheel zoom
  // is unconditional. Double-click resets to identity.
  useEffect(() => {
    const svgEl = svgRef.current;
    const groupEl = zoomGroupRef.current;
    if (!svgEl || !groupEl) return;
    const svg = select(svgEl);
    const g = select(groupEl);
    const z = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 5])
      .filter((event: Event) => {
        // Allow wheel zoom + double-click anywhere; only allow drag-pan
        // when the source is the SVG background (not a node, band, or
        // badge). This keeps band hover/click intact.
        if (event.type === "wheel" || event.type === "dblclick") return true;
        const target = event.target as Element | null;
        if (!target) return false;
        // EXCLUDE clicks/drags on interactive elements; allow on SVG /
        // background / mask <path>.
        const tag = target.tagName.toLowerCase();
        if (tag === "svg") return true;
        if (target.classList?.contains("sankey-bg")) return true;
        // path/rect/text/g inside zoom group → don't pan.
        return false;
      })
      .on("zoom", (event) => {
        const t = event.transform;
        g.attr("transform", `translate(${t.x}, ${t.y}) scale(${t.k})`);
        setZoomScale(t.k);
      });
    svg.call(z);
    zoomBehaviorRef.current = z;
    // Reset on mount so the layout starts at 1× regardless of prior state.
    svg.call(z.transform, zoomIdentity);
    return () => {
      svg.on(".zoom", null);
    };
  }, [nodes.length, links.length]);

  // Button-driven zoom anchors on the SVG's visible centre so the
  // graph doesn't drift away from where the user is looking. Without
  // an explicit centre, d3-zoom's scaleBy uses an undefined anchor
  // and the drift becomes visually unsettling.
  const handleZoomBy = (factor: number) => {
    const svgEl = svgRef.current;
    const z = zoomBehaviorRef.current;
    if (!svgEl || !z) return;
    const r = svgEl.getBoundingClientRect();
    select(svgEl).call(z.scaleBy, factor, [r.width / 2, r.height / 2]);
  };
  const handleZoomIn = () => handleZoomBy(1.4);
  const handleZoomOut = () => handleZoomBy(0.71);

  // Copy a shareable URL that reproduces the current Sankey state
  // (drill, filter chips, compare mode, sink visibility). The URL
  // hook itself debounces writes, so just await the next tick before
  // reading window.location.href to ensure the latest state is on it.
  const handleCopyLink = async () => {
    await new Promise<void>((r) => setTimeout(r, 220));   // ≥ debounce window
    try {
      await navigator.clipboard.writeText(buildShareLink());
      toast.success("Link copied — open it in any tab to restore this view");
    } catch {
      toast.error("Could not copy to clipboard");
    }
  };
  const handleZoomReset = () => {
    const svgEl = svgRef.current;
    const z = zoomBehaviorRef.current;
    if (svgEl && z) select(svgEl).call(z.transform, zoomIdentity);
  };

  // Identify the absolute leftmost / rightmost column x-positions so
  // label placement only puts side-anchored labels at the canvas edges.
  // Anything in between goes ABOVE its bar — preventing adjacent columns
  // from competing for the same horizontal label slot.
  const { minColX, maxColX } = useMemo(() => {
    if (nodes.length === 0) return { minColX: 0, maxColX: 0 };
    let mn = Infinity, mx = -Infinity;
    for (const n of nodes) {
      if (n.x0 < mn) mn = n.x0;
      if (n.x0 > mx) mx = n.x0;
    }
    return { minColX: mn, maxColX: mx };
  }, [nodes]);

  // Combined dim source: explicit drill (click) OR external column trace
  // (hover from grid). When a column trace is active and the node isn't
  // in the trace set, the band/node dims.
  const isOnTrace = (id: string): boolean => {
    if (!tracedNodeIds) return true;
    return tracedNodeIds.has(id);
  };

  // Save the SVG as a PNG. Rasterise via canvas, download.
  const handleSavePng = async () => {
    const svg = svgRef.current;
    if (!svg) return;
    try {
      const xml = new XMLSerializer().serializeToString(svg);
      const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
      const img = new Image();
      img.crossOrigin = "anonymous";
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = (e) => reject(e);
        img.src = url;
      });
      const canvas = document.createElement("canvas");
      // Render at 2x for retina sharpness.
      const scale = 2;
      canvas.width = (svg.clientWidth || width) * scale;
      canvas.height = layout.height * scale;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("canvas 2d unsupported");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0);
      const png = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = png;
      a.download = `${(doc.name || "pipeline").replace(/[^\w-]+/g, "_")}-sankey.png`;
      a.click();
      toast.success("Saved Sankey as PNG");
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  };

  // Print just the Sankey SVG. Open a tiny new window with the SVG and
  // call print() — preserves vectors, much sharper than rasterising.
  const handlePrint = () => {
    const svg = svgRef.current;
    if (!svg) return;
    const xml = new XMLSerializer().serializeToString(svg);
    const w = window.open("", "_blank", "width=1200,height=800");
    if (!w) {
      toast.error("Print blocked — allow popups for this site");
      return;
    }
    w.document.write(`
      <!DOCTYPE html><html><head><title>${doc.name ?? "Pipeline"} — Sankey</title>
      <style>
        body { margin:0; padding:24px; font-family:system-ui,sans-serif; }
        h1 { font-size:14px; font-weight:600; margin:0 0 12px; }
        @media print { body { padding:0; } h1 { display:none; } }
      </style></head><body>
      <h1>${doc.name ?? "Pipeline"} — Volume view</h1>
      ${xml}
      <script>setTimeout(() => window.print(), 200);</script>
      </body></html>
    `);
    w.document.close();
  };

  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-background/95 backdrop-blur">
      {/* Toolbar — close + actions + legend */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border bg-card/80">
        <span className="text-sm font-semibold flex items-center gap-1.5">
          <span aria-hidden>🌊</span>
          Volume view (Sankey)
        </span>
        <span className="text-xs text-muted-foreground">
          width = row count · color = operation type
        </span>
        {tracedNodeIds && (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border border-emerald-300/40">
            🔗 column trace active
          </span>
        )}
        <span className="flex-1" />
        <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground select-none cursor-pointer">
          <input
            type="checkbox"
            checked={showSinks}
            onChange={(e) => setShowSinks(e.target.checked)}
            className="accent-emerald-600"
          />
          Show output sinks
        </label>
        <button
          type="button"
          onClick={() => setCompareMode((v) => !v)}
          title="Overlay deltas vs the previous succeeded run"
          className={[
            "text-xs px-2.5 py-1 rounded border transition-colors flex items-center gap-1",
            compareMode
              ? "bg-amber-100 dark:bg-amber-900/40 border-amber-300 text-amber-900 dark:text-amber-100"
              : "border-border bg-card hover:bg-muted text-foreground/80",
          ].join(" ")}
        >
          <span aria-hidden>📊</span> Compare runs
        </button>
        <button
          type="button"
          onClick={() => setAnnotateMode((v) => !v)}
          title="Click any band to drop or edit a note"
          className={[
            "text-xs px-2.5 py-1 rounded border transition-colors flex items-center gap-1",
            annotateMode
              ? "bg-amber-100 dark:bg-amber-900/40 border-amber-300 text-amber-900 dark:text-amber-100"
              : "border-border bg-card hover:bg-muted text-foreground/80",
          ].join(" ")}
        >
          <span aria-hidden>📌</span> Annotate
        </button>
        {/* Zoom controls. Scroll-wheel + drag-pan are also live; these
            buttons exist for users who don't realise direct manipulation
            works (Nielsen-style "discoverability" rule). */}
        <div className="flex items-center rounded border border-border bg-card overflow-hidden">
          <button
            type="button"
            onClick={handleZoomOut}
            title="Zoom out (or scroll on the diagram)"
            className="text-xs px-2 py-1 hover:bg-muted text-foreground/80 transition-colors"
          >
            −
          </button>
          <span className="text-[10px] font-mono tabular-nums px-2 text-muted-foreground border-x border-border min-w-[42px] text-center select-none">
            {Math.round(zoomScale * 100)}%
          </span>
          <button
            type="button"
            onClick={handleZoomIn}
            title="Zoom in"
            className="text-xs px-2 py-1 hover:bg-muted text-foreground/80 transition-colors"
          >
            +
          </button>
          <button
            type="button"
            onClick={handleZoomReset}
            title="Reset zoom (fit to default)"
            className="text-xs px-2 py-1 hover:bg-muted text-foreground/80 transition-colors border-l border-border"
          >
            ⤢
          </button>
        </div>
        <button
          type="button"
          onClick={handleCopyLink}
          title="Copy a link that restores this exact view (drill, filter, compare mode)"
          className="text-xs px-2.5 py-1 rounded border border-border bg-card hover:bg-muted text-foreground/80 transition-colors flex items-center gap-1"
        >
          <span aria-hidden>🔗</span> Copy link
        </button>
        <button
          type="button"
          onClick={handleSavePng}
          title="Save the diagram as a PNG"
          className="text-xs px-2.5 py-1 rounded border border-border bg-card hover:bg-muted text-foreground/80 transition-colors flex items-center gap-1"
        >
          <span aria-hidden>💾</span> Save PNG
        </button>
        <button
          type="button"
          onClick={handlePrint}
          title="Print the diagram"
          className="text-xs px-2.5 py-1 rounded border border-border bg-card hover:bg-muted text-foreground/80 transition-colors flex items-center gap-1"
        >
          <span aria-hidden>🖨</span> Print
        </button>
        <button
          type="button"
          onClick={onClose}
          className="text-xs px-2.5 py-1 rounded bg-muted hover:bg-muted/80 text-foreground/80 transition-colors"
        >
          ← Back to canvas
        </button>
      </div>

      {/* Tier 3 — interactive legend. Each chip is a toggle that
          isolates that op kind across the diagram. Multiple chips can
          stack (Filter + Aggregate, e.g.). Click a chip again or any
          dimmed area to clear. */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-2 text-[11px] border-b border-border/60 bg-muted/20">
        <span className="text-muted-foreground mr-1">Filter by op:</span>
        {(Object.keys(OP_COLORS) as OpKind[]).map((op) => {
          const active = activeKinds.has(op);
          const anyActive = activeKinds.size > 0;
          return (
            <button
              key={op}
              type="button"
              onClick={() => toggleKindFilter(op)}
              className={[
                "flex items-center gap-1.5 px-2 py-0.5 rounded border transition-all",
                active
                  ? "border-foreground/40 bg-card shadow-sm text-foreground"
                  : anyActive
                    ? "border-transparent text-muted-foreground/60 hover:text-foreground/70"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:bg-card/50",
              ].join(" ")}
            >
              <span
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: OP_COLORS[op].fill }}
              />
              {OP_COLORS[op].emoji} {OP_COLORS[op].label}
            </button>
          );
        })}
        {activeKinds.size > 0 && (
          <button
            type="button"
            onClick={() => setActiveKinds(new Set())}
            className="ml-1 text-[10px] text-muted-foreground hover:text-foreground underline underline-offset-2"
          >
            clear filter
          </button>
        )}
      </div>

      {/* Canvas */}
      <div className="flex-1 overflow-auto bg-zinc-50 dark:bg-zinc-950/40 p-4 relative">
        {nodes.length === 0 ? (
          <div className="h-full grid place-items-center text-sm text-muted-foreground italic">
            No row-count metrics available — run the pipeline first.
          </div>
        ) : (
          <svg
            ref={svgRef}
            width={width}
            height={layout.height}
            viewBox={`0 0 ${width} ${layout.height}`}
            className="block mx-auto cursor-grab active:cursor-grabbing"
          >
            {/* Background rect catches drag-pan events. d3-zoom's filter
                allows pan only when initiated on this rect (or the SVG
                itself), so band hover/click stays intact. */}
            <rect
              className="sankey-bg"
              x={0}
              y={0}
              width={width}
              height={layout.height}
              fill="transparent"
            />
            <defs>
              {/* Subtle drop-shadow under node bars so they sit ABOVE
                  the band river instead of looking embedded in it. */}
              <filter id="sankey-bar-shadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="1" stdDeviation="1.2" floodOpacity="0.18" />
              </filter>
              {/* Per-link gradient so the band fades from source op to
                  target op color. Subtle but visually rich. */}
              {links.map((l, i) => (
                <linearGradient
                  key={i}
                  id={`sgrad-${i}`}
                  gradientUnits="userSpaceOnUse"
                  x1={l.source.x1}
                  x2={l.target.x0}
                >
                  <stop offset="0%" stopColor={OP_COLORS[l.source.op].flow} />
                  <stop offset="100%" stopColor={OP_COLORS[l.target.op].flow} />
                </linearGradient>
              ))}
            </defs>

            {/* Zoom-pan group: every visible drawing primitive lives
                inside this <g>, so a single transform on it pans + zooms
                the whole diagram. d3-zoom updates the transform via the
                useEffect bound on `svgRef`. */}
            <g ref={zoomGroupRef}>

            {/* Bands first so node rectangles render on top.
                Each band is interactive: hover for a tooltip, click
                anchors the source node so the full lineage chain
                (upstream + downstream) stays bright while everything
                else dims. */}
            {links.map((l, i) => {
              const dim = isLinkDim(l);
              const path = sankeyLinkHorizontal()({
                source: { x1: l.source.x1, y0: l.y0, y1: l.y0 } as never,
                target: { x0: l.target.x0, y0: l.y1, y1: l.y1 } as never,
                width: l.width,
                y0: l.y0,
                y1: l.y1,
              } as never) as string | null;
              if (!path) return null;
              // Tier 2: bands fade in left-to-right based on source x —
              // creates a brief "data flowing into view" wave on first
              // render. The delay is small enough to feel snappy, big
              // enough to read as motion.
              const xNorm = Math.max(0, Math.min(1, l.source.x1 / Math.max(width, 1)));
              return (
                <motion.path
                  key={i}
                  initial={{ opacity: 0 }}
                  d={path}
                  fill="none"
                  stroke={`url(#sgrad-${i})`}
                  strokeWidth={Math.max(1, l.width)}
                  animate={{ opacity: dim ? 0.12 : 1 }}
                  transition={{
                    opacity: { duration: 0.45, delay: xNorm * 0.35, ease: "easeOut" },
                  }}
                  style={{ cursor: "pointer" }}
                  onMouseEnter={(e) => {
                    const svgRect = svgRef.current?.getBoundingClientRect();
                    setHoverLink({
                      idx: i,
                      x: e.clientX - (svgRect?.left ?? 0),
                      y: e.clientY - (svgRect?.top ?? 0),
                    });
                  }}
                  onMouseMove={(e) => {
                    const svgRect = svgRef.current?.getBoundingClientRect();
                    setHoverLink({
                      idx: i,
                      x: e.clientX - (svgRect?.left ?? 0),
                      y: e.clientY - (svgRect?.top ?? 0),
                    });
                  }}
                  onMouseLeave={() => setHoverLink(null)}
                  onClick={() => {
                    if (annotateMode) {
                      handleAnnotate(linkKey(l));
                    } else {
                      setDrill((cur) => (cur === l.source.id ? null : l.source.id));
                    }
                  }}
                />
              );
            })}

            {/* Row-count badges directly on the bands. Only emitted when
                the band is fat enough to be readable; tiny bands stay
                clean and rely on the hover tooltip instead. */}
            {links.map((l, i) => {
              if (l.width < 14) return null;
              const dim = isLinkDim(l);
              const midX = (l.source.x1 + l.target.x0) / 2;
              const midY = (l.y0 + l.y1) / 2;
              const xNorm = Math.max(0, Math.min(1, l.source.x1 / Math.max(width, 1)));

              // Tier 3 compare-runs: render the delta vs prior run
              // alongside the row count when compareMode is on.
              let deltaText = "";
              let deltaColor = "";
              if (compareMode && previousMetrics) {
                const prevTargetRows = previousMetrics[l.target.id]?.rows_out ?? null;
                if (prevTargetRows != null && prevTargetRows > 0) {
                  const pct = ((l.value - prevTargetRows) / prevTargetRows) * 100;
                  if (Math.abs(pct) >= 0.5) {
                    deltaText = ` ${pct >= 0 ? "▲" : "▼"}${Math.abs(pct).toFixed(0)}%`;
                    deltaColor = pct >= 0 ? "rgb(134 239 172)" : "rgb(252 165 165)";
                  } else {
                    deltaText = " =";
                    deltaColor = "rgb(212 212 216)";
                  }
                }
              }

              return (
                <motion.text
                  key={`badge-${i}`}
                  initial={{ opacity: 0 }}
                  x={midX}
                  y={midY}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  pointerEvents="none"
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    fill: "white",
                    paintOrder: "stroke",
                    stroke: "rgba(15, 23, 42, 0.55)",
                    strokeWidth: 3,
                  }}
                  animate={{ opacity: dim ? 0 : 1 }}
                  transition={{
                    opacity: { duration: 0.45, delay: xNorm * 0.35 + 0.2, ease: "easeOut" },
                  }}
                >
                  {formatRows(l.value)}
                  {deltaText && (
                    <tspan style={{ fill: deltaColor }}>{deltaText}</tspan>
                  )}
                </motion.text>
              );
            })}

            {/* Tier 3: annotation pins. One small badge per band that
                has a saved note. Hover for tooltip via title. Clicking
                in annotateMode also lets the user edit the existing
                note, so this is the primary edit surface too. */}
            {links.map((l, i) => {
              const key = linkKey(l);
              const note = annotations[key];
              if (!note) return null;
              if (isLinkDim(l)) return null;
              const px = (l.source.x1 + l.target.x0) / 2;
              const py = (l.y0 + l.y1) / 2 + Math.max(8, l.width / 2 + 4);
              return (
                <g key={`annot-${i}`} style={{ cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); handleAnnotate(key); }}>
                  <title>{note}</title>
                  <circle cx={px} cy={py} r={9} fill="rgb(245 158 11)" stroke="white" strokeWidth={2} />
                  <text
                    x={px}
                    y={py + 0.5}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ fontSize: 11, fontWeight: 700, fill: "white", pointerEvents: "none" }}
                  >
                    📌
                  </text>
                </g>
              );
            })}

            {/* Node rectangles + labels.
                Label-collision policy: middle-column nodes (not leftmost,
                not rightmost) get their labels stacked ABOVE the bar
                (text-anchor: middle). That keeps each label inside its
                OWN column slot — adjacent column labels can't run into
                each other no matter how wide they are. Source/sink
                nodes still get side-anchored labels because they're at
                the canvas edges and have plenty of horizontal room. */}
            {nodes.map((n) => {
              const dim = isNodeDim(n.id, n.op);
              // Edge columns get side labels (room to spread). Every
              // interior column gets its label stacked ABOVE its own
              // bar so adjacent labels can't collide.
              const isLeftMost = n.x0 === minColX;
              const isRightMost = n.x0 === maxColX;
              const labelMode: "right" | "left" | "above" =
                isLeftMost ? "right" : isRightMost ? "left" : "above";
              const labelX =
                labelMode === "right" ? n.x1 + 6
                : labelMode === "left" ? n.x0 - 6
                : (n.x0 + n.x1) / 2;
              const anchor: "start" | "middle" | "end" =
                labelMode === "right" ? "start"
                : labelMode === "left" ? "end"
                : "middle";
              const labelY1 =
                labelMode === "above" ? n.y0 - 18 : (n.y0 + n.y1) / 2 - 2;
              const labelY2 =
                labelMode === "above" ? n.y0 - 6 : (n.y0 + n.y1) / 2 + 12;
              return (
                <motion.g
                  key={n.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: dim ? 0.18 : 1 }}
                  transition={{
                    opacity: {
                      duration: 0.4,
                      delay: Math.max(0, Math.min(1, n.x0 / Math.max(width, 1))) * 0.35,
                      ease: "easeOut",
                    },
                  }}
                  style={{ cursor: "pointer" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setDrill((cur) => (cur === n.id ? null : n.id));
                  }}
                >
                  <rect
                    x={n.x0}
                    y={n.y0}
                    width={n.x1 - n.x0}
                    height={Math.max(1, n.y1 - n.y0)}
                    fill={OP_COLORS[n.op].fill}
                    rx={5}
                    filter="url(#sankey-bar-shadow)"
                  />
                  <text
                    x={labelX}
                    y={labelY1}
                    textAnchor={anchor}
                    dominantBaseline="middle"
                    style={{ fontSize: 13, fontWeight: 700, letterSpacing: "-0.01em" }}
                    className="fill-zinc-900 dark:fill-zinc-50"
                  >
                    {n.emoji ? `${n.emoji} ` : ""}
                    {n.label}
                  </text>
                  <text
                    x={labelX}
                    y={labelY2}
                    textAnchor={anchor}
                    dominantBaseline="middle"
                    style={{ fontSize: 10, fontFamily: "ui-monospace, monospace" }}
                    className="fill-zinc-500 dark:fill-zinc-400"
                  >
                    {n.rows != null ? `${formatRows(n.rows)} rows` : "—"}
                  </text>
                </motion.g>
              );
            })}

            </g>
          </svg>
        )}

        {/* Hover tooltip on bands. Floats next to the cursor with the
            band's source → target labels, row count, and % of source.
            Pure presentation — pointer-events-none so the band itself
            stays interactive. */}
        {hoverLink && (() => {
          const l = links[hoverLink.idx];
          if (!l) return null;
          const sourceTotal = sourceOutTotals[l.source.id] || 1;
          const pct = (l.value / sourceTotal) * 100;
          const svgRect = svgRef.current?.getBoundingClientRect();
          const containerLeft = svgRect ? svgRect.left - (svgRef.current?.parentElement?.getBoundingClientRect().left ?? 0) : 0;
          return (
            <div
              className="pointer-events-none absolute z-30 rounded-md border border-border bg-card/95 backdrop-blur shadow-lg px-3 py-2 text-[11px] leading-relaxed"
              style={{
                left: hoverLink.x + containerLeft + 12,
                top: hoverLink.y + 12,
                maxWidth: 280,
              }}
            >
              <div className="flex items-center gap-1.5 font-semibold text-foreground">
                <span aria-hidden>{OP_COLORS[l.source.op].emoji}</span>
                <span className="truncate">{l.source.label}</span>
                <span className="text-muted-foreground">→</span>
                <span aria-hidden>{OP_COLORS[l.target.op].emoji}</span>
                <span className="truncate">{l.target.label}</span>
              </div>
              <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-muted-foreground font-mono text-[10px]">
                <span>rows</span>
                <span className="text-foreground font-semibold">{formatRows(l.value)}</span>
                <span>% of source</span>
                <span className="text-foreground font-semibold">{pct.toFixed(1)}%</span>
                <span>op</span>
                <span className="text-foreground">{OP_COLORS[l.target.op].label}</span>
              </div>
            </div>
          );
        })()}

        <AnimatePresence>
          {drill && (() => {
            const n = nodes.find((x) => x.id === drill);
            if (!n) return null;
            return (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                className="mx-auto mt-4 max-w-3xl rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-card shadow-sm overflow-hidden"
              >
                <div className="flex items-center gap-3 px-4 py-3 bg-emerald-50/40 dark:bg-emerald-950/20 border-b border-border">
                  <span aria-hidden className="text-2xl">{n.emoji ?? "📦"}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold">{n.label}</div>
                    <div className="text-[11px] text-muted-foreground font-mono">
                      {OP_COLORS[n.op].label}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDrill(null)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    ✕
                  </button>
                </div>
                <div className="p-4 grid grid-cols-3 gap-3 text-xs">
                  <Stat label="Rows" value={n.rows != null ? formatRows(n.rows) : "—"} />
                  <Stat
                    label="Inputs"
                    value={String(links.filter((l) => l.target.id === drill).length)}
                  />
                  <Stat
                    label="Outputs"
                    value={String(links.filter((l) => l.source.id === drill).length)}
                  />
                </div>
              </motion.div>
            );
          })()}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono">
        {label}
      </div>
      <div className="text-sm font-semibold mt-0.5">{value}</div>
    </div>
  );
}

function formatRows(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(n < 10_000_000 ? 1 : 0)}M`;
  return `${(n / 1_000_000_000).toFixed(1)}B`;
}

// ---- buildSankey -------------------------------------------------------

function buildSankey(
  doc: PipelineDocument,
  manifests: Record<string, StepManifest>,
  nodeMetrics: Record<string, NodeRunMetrics> | undefined,
  width: number,
  baseHeight: number,
  showSinks: boolean,
): { nodes: SankeyNodeOut[]; links: SankeyLinkOut[]; layout: { height: number } } {
  // d3-sankey lays out nodes in columns by depth. To keep bands from
  // overlapping when a column has many nodes, height needs to scale
  // with the WORST-CASE column density. Compute that in two passes:
  // first a quick depth+count pass to size the canvas, then the real
  // sankey pass with the computed extent.
  //
  // Per-node minimum vertical budget = NODE_MIN_HEIGHT + NODE_PAD. With
  // 14 nodes in the worst column we want ≈ 14 × 84 = 1176px tall.
  const NODE_MIN_HEIGHT = 28;
  const NODE_PAD = 56;
  const NODE_WIDTH = 28;
  const SIDE_MARGIN = 200;
  const sankeyNodes: SankeyNodeIn[] = [];
  const sankeyLinks: SankeyLinkIn[] = [];

  // Datasets become source nodes. Use the dataset's known rowCount (we
  // pass it via doc but it isn't usually populated here, so fall through
  // to the upstream node's row count).
  for (const d of doc.datasets) {
    sankeyNodes.push({
      id: d.id,
      label: d.label || d.id,
      op: "source",
      rows: null,   // datasets don't have nodeMetrics; rows come from downstream
      emoji: "📥",
      isDataset: true,
    });
  }

  // Step nodes
  for (const n of doc.nodes) {
    const m = manifests[n.step];
    const metrics = nodeMetrics?.[n.id];
    sankeyNodes.push({
      id: n.id,
      label: (n.ui?.label ?? m?.label ?? n.step) as string,
      op: opKindForStep(n.step, m),
      rows: metrics?.rows_out ?? null,
      emoji: undefined,
    });
  }

  // Edges from inputs
  for (const n of doc.nodes) {
    for (const ref of Object.values(n.inputs ?? {})) {
      const targetMetrics = nodeMetrics?.[n.id];
      const targetRows = targetMetrics?.rows_out ?? null;
      const m = manifests[n.step];
      // Use the TARGET's row count for the band width — the band
      // visually shows how much data comes OUT of the source TO this
      // target. d3-sankey requires positive values; floor at 1.
      const value = Math.max(1, targetRows ?? 1);
      sankeyLinks.push({
        source: ref.ref,
        target: n.id,
        value,
        op: opKindForStep(n.step, m),
      });
    }
  }

  // Optionally drop pure-output sinks (image exports, file writes).
  // They're terminal mirrors of upstream data — they tell the volume
  // story nothing new and clutter the rightmost column. Toggle in the
  // toolbar restores them.
  const sinkIds = new Set<string>();
  if (!showSinks) {
    for (const n of sankeyNodes) {
      if (n.op === "sink") sinkIds.add(n.id);
    }
  }
  const linksAfterSinkFilter = sinkIds.size === 0
    ? sankeyLinks
    : sankeyLinks.filter((l) => !sinkIds.has(l.source) && !sinkIds.has(l.target));
  const nodesAfterSinkFilter = sinkIds.size === 0
    ? sankeyNodes
    : sankeyNodes.filter((n) => !sinkIds.has(n.id));

  // Drop nodes that have no edges (orphan datasets etc.) — d3-sankey
  // throws on those.
  const referenced = new Set<string>();
  for (const l of linksAfterSinkFilter) {
    referenced.add(l.source);
    referenced.add(l.target);
  }
  const filteredNodes = nodesAfterSinkFilter.filter((n) => referenced.has(n.id));

  if (filteredNodes.length === 0 || linksAfterSinkFilter.length === 0) {
    return { nodes: [], links: [], layout: { height: baseHeight } };
  }

  // First pass: estimate per-column density to pick a height that
  // doesn't overlap bands. We do a cheap topo levelizer just like
  // sankeyJustify will run internally — count incoming edges per node
  // and pseudo-rank them.
  const inDeg: Record<string, number> = {};
  const adj: Record<string, string[]> = {};
  for (const n of filteredNodes) {
    inDeg[n.id] = 0;
    adj[n.id] = [];
  }
  for (const l of linksAfterSinkFilter) {
    inDeg[l.target] = (inDeg[l.target] ?? 0) + 1;
    (adj[l.source] ??= []).push(l.target);
  }
  const depth: Record<string, number> = {};
  const stack: string[] = filteredNodes.filter((n) => inDeg[n.id] === 0).map((n) => n.id);
  for (const id of stack) depth[id] = 0;
  while (stack.length > 0) {
    const id = stack.shift()!;
    for (const c of adj[id] ?? []) {
      depth[c] = Math.max(depth[c] ?? 0, depth[id] + 1);
      stack.push(c);
    }
  }
  // sankeyLeft places nodes at their NATURAL depth (longest path from
  // a source) — no terminal-stacking trick. The depth map we computed
  // above already matches that, so leave it alone.
  const colCounts: Record<number, number> = {};
  for (const n of filteredNodes) {
    const d = depth[n.id] ?? 0;
    colCounts[d] = (colCounts[d] ?? 0) + 1;
  }
  const worstCol = Math.max(1, ...Object.values(colCounts));

  // Height: enough vertical room that the worst column can lay out its
  // nodes with full padding, plus 48px margin. Floor at baseHeight so
  // small pipelines still render at a comfortable size.
  const computedHeight = Math.max(
    baseHeight,
    worstCol * (NODE_MIN_HEIGHT + NODE_PAD) + 48,
  );

  const layout = sankey<SankeyNodeIn, SankeyLinkIn>()
    .nodeId((d) => d.id)
    // sankeyLeft anchors sources at the leftmost column but lets each
    // terminal find its NATURAL depth (longest path from a source).
    // sankeyJustify forces all terminals to the rightmost column, which
    // looks bad when one terminal has a long chain and another is just
    // 1 hop off a mid-pipeline node — they get stacked far apart.
    .nodeAlign(sankeyLeft)
    .nodePadding(NODE_PAD)
    .nodeWidth(NODE_WIDTH)
    .extent([[SIDE_MARGIN, 32], [width - SIDE_MARGIN, computedHeight - 32]]);

  const graph = layout({
    nodes: filteredNodes.map((n) => ({ ...n })),
    links: linksAfterSinkFilter.map((l) => ({ ...l })),
  });

  return {
    nodes: graph.nodes as unknown as SankeyNodeOut[],
    links: graph.links as unknown as SankeyLinkOut[],
    layout: { height: computedHeight },
  };
}

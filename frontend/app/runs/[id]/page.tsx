"use client";

/**
 * Single-run detail page.
 *
 * Shows everything DIG knows about one executed job:
 *   - Header: pipeline + status + duration + tags + "open editor" link
 *   - Inputs: dataset references the run consumed, with shape
 *   - Outputs: parquet snapshots produced, with URI / row count / schema
 *   - Per-node timeline: status + elapsed_ms + rows_out, expandable to columns
 *   - Errors: when the run failed
 *
 * Reference data note: even though we don't yet capture full
 * `InputRef` records at ingest, we DO have:
 *   - the pipeline document's dataset references (input URIs + types),
 *   - the per-node `columns` field on `nodeMetrics` (output schema for
 *     terminal nodes — populated since the previous release),
 *   - row counts per terminal node.
 * Those three together cover both the incoming-shape and outgoing-shape
 * record the user asked for.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

import { api, type RunOut, API_BASE, getApiToken } from "@/lib/api/client";
import { fmtDuration, fmtInt } from "@/lib/format-number";
import { useDocumentTitle } from "@/lib/use-document-title";
import { PositiveLoader } from "@/components/positive-loader";

const STATUS_META: Record<string, { emoji: string; tone: string; label: string; bg: string }> = {
  succeeded: { emoji: "✅", tone: "text-emerald-700 dark:text-emerald-300", bg: "bg-emerald-50 dark:bg-emerald-950/40", label: "Succeeded" },
  running:   { emoji: "🌀", tone: "text-sky-700 dark:text-sky-300",       bg: "bg-sky-50 dark:bg-sky-950/40",       label: "Running" },
  failed:    { emoji: "❌", tone: "text-rose-700 dark:text-rose-300",     bg: "bg-rose-50 dark:bg-rose-950/40",     label: "Failed" },
  queued:    { emoji: "⏳", tone: "text-zinc-600 dark:text-zinc-400",     bg: "bg-zinc-50 dark:bg-zinc-950/30",     label: "Queued" },
  cancelled: { emoji: "🛑", tone: "text-zinc-500 dark:text-zinc-400",     bg: "bg-zinc-50 dark:bg-zinc-950/30",     label: "Cancelled" },
};
function statusMeta(s: string) {
  return STATUS_META[s] ?? { emoji: "❔", tone: "text-zinc-500", bg: "bg-zinc-50", label: s };
}

function parseUtcMs(iso: string | null): number | null {
  if (!iso) return null;
  const s = iso.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const t = new Date(s).getTime();
  return Number.isNaN(t) ? null : t;
}

// Per-node metric — shape comes from the executor.
interface NodeMetric {
  status?: string;
  rows_out?: number | null;
  elapsed_ms?: number | null;
  error?: string;
  columns?: string[];
  finished_at_ms?: number;
}

// ---- Page --------------------------------------------------------------

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;

  const runQ = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId),
    enabled: !!runId,
    refetchInterval: (q) => {
      // Auto-refresh while the run is still in-flight; stop once it
      // settles. 2 s polling is enough for a UX that "feels live"
      // without flooding the API.
      const status = (q.state.data as RunOut | undefined)?.status;
      return status === "running" || status === "queued" ? 2000 : false;
    },
  });

  // Fetch the pipeline document so we can render dataset (input)
  // references + group node ids → labels in the timeline.
  const pipelineId = runQ.data?.pipelineId;

  // Re-run this pipeline and follow the new run. Previously the button was a
  // link into the editor, which started nothing.
  const router = useRouter();
  const rerun = useMutation({
    mutationFn: () => api.startRun(pipelineId!),
    onSuccess: (r) => {
      toast.success("▶️ Run started");
      router.push(`/runs/${r.id}`);
    },
    onError: (e: Error) => toast.error(`Couldn't start the run: ${e.message}`),
  });
  const pipelineQ = useQuery({
    queryKey: ["pipeline", pipelineId],
    queryFn: () => api.getPipeline(pipelineId!),
    enabled: !!pipelineId,
    staleTime: 60_000,
  });

  const run = runQ.data;
  const doc = pipelineQ.data?.document as
    | { name?: string; nodes?: Array<{ id: string; step: string; ui?: { label?: string } }>; datasets?: Array<{ id: string; label?: string; uri?: string; connector?: string }>; outputs?: Array<{ id: string; name: string; from?: { ref: string } }> }
    | undefined;
  useDocumentTitle(
    doc?.name
      ? `Run · ${doc.name} · ${run?.status ?? "loading"}`
      : run
        ? `Run · ${run.status}`
        : "Run",
  );

  if (runQ.isLoading) {
    return (
      <main className="h-screen grid place-items-center">
        <PositiveLoader variant="rendering" primary="Loading run…" size="md" showTimer={false} />
      </main>
    );
  }
  if (!run) {
    return (
      <main id="main" className="h-screen grid place-items-center p-6">
        <div className="text-center space-y-4 max-w-md">
          <div className="text-5xl" aria-hidden>🔎</div>
          <h1 className="text-lg font-semibold">Run not found</h1>
          <p className="text-sm text-muted-foreground">
            This run may have been deleted, or the link may be from a different workspace.
          </p>
          <div className="flex items-center justify-center gap-2 pt-2">
            <Link href="/runs" className="text-xs px-3 py-1.5 rounded-md border border-border bg-card hover:bg-muted">
              ← Back to runs
            </Link>
            <Link href="/" className="text-xs px-3 py-1.5 rounded-md hover:bg-muted text-muted-foreground">
              Home
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const m = statusMeta(run.status);
  const startedMs = parseUtcMs(run.startedAt ?? null);
  const finishedMs = parseUtcMs(run.finishedAt ?? null);
  const durationMs =
    startedMs && finishedMs ? Math.max(0, finishedMs - startedMs) : null;

  return (
    <main id="main" className="flex flex-col h-screen overflow-hidden">
      {/* Header */}
      <header className="px-6 py-3 border-b border-border flex items-center gap-3 shrink-0">
        <Link
          href="/runs"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          ← Runs
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700">·</span>
        <span className={`flex items-center gap-1.5 text-sm font-semibold ${m.tone}`}>
          <span aria-hidden className="text-base">{m.emoji}</span>
          {m.label}
        </span>
        <span className="text-zinc-300 dark:text-zinc-700">·</span>
        <h1 className="text-base font-medium tracking-tight truncate">
          {doc?.name ?? run.pipelineId}
        </h1>
        <button
          type="button"
          title={`Copy run id · ${run.id}`}
          aria-label={`Copy full run id ${run.id}`}
          onClick={() => {
            try {
              navigator.clipboard.writeText(run.id);
              toast.success("Run id copied");
            } catch {
              toast.error("Clipboard unavailable");
            }
          }}
          className="text-[10px] font-mono text-muted-foreground/60 tabular-nums hover:text-foreground inline-flex items-center gap-1 transition-colors"
        >
          run {run.id.slice(0, 12)}… <span aria-hidden>📋</span>
        </button>
        <span className="flex-1" />
        <Link
          href={`/pipelines/${run.pipelineId}`}
          className="text-xs px-2.5 py-1 rounded border border-border bg-card hover:bg-muted text-foreground/80 transition-colors flex items-center gap-1"
        >
          <span aria-hidden>🛤</span> Open in editor
        </Link>
      </header>

      <div className="flex-1 overflow-y-auto relative" id="run-scroll">
        {/* Width scales: max-w-5xl on standard laptop screens, expanding
            to max-w-7xl on 1440px+ (xl) and removing the cap on 1920px+
            (2xl) so the chart artifacts get the breathing room they deserve
            on ultrawide / external monitors. Round-3 UX finding: the
            previous fixed max-w-5xl wasted ~30–47% horizontal space at
            ≥ 1920px. */}
        <div className="max-w-5xl xl:max-w-7xl 2xl:max-w-[1600px] mx-auto px-6 py-6 space-y-6">
          {/* Stats strip — Round-4 UX#3: ``grid-cols-2 md:grid-cols-5``
              left a gap at the sm breakpoint where two columns of
              long timestamps wrapped onto separate lines. Add an
              intermediate 3-column step so 640..1023px renders cleanly. */}
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <Stat label="Started" value={startedMs ? new Date(startedMs).toLocaleString() : "—"} />
            <Stat label="Finished" value={finishedMs ? new Date(finishedMs).toLocaleString() : "—"} />
            <Stat label="Duration" value={fmtDuration(durationMs)} mono />
            <Stat label="Outputs" value={String(run.outputPaths?.length ?? 0)} mono />
            <Stat label="Nodes ran" value={String(Object.keys(run.nodeMetrics ?? {}).length)} mono />
          </section>

          {/* Error panel — only when failed. Round-3 UX finding: previously
              showed only the raw exception text with no step / node
              identification and no recovery action. We now (1) extract
              the failing node id from common error-message patterns, (2)
              link to the editor focused on that node, and (3) offer a
              "Re-run pipeline" action. */}
          {run.error && (() => {
            // Extract node id from messages like:
            //   "polars step 'n_chart_map' (export_to_map) failed: ..."
            //   "step 'n_xyz' is not a Polars-engine step ..."
            //   "node 'n_abc' missing input ..."
            // Round-9 fix: include `-` in the character class so node ids
            // like ``n-abc-123`` link correctly. (User-friendly labels in
            // step.ui.label can also be referenced.)
            const nodeMatch = run.error.match(/(?:polars step|step|node)\s+['"]([A-Za-z0-9_-]+)['"]/);
            const failedNodeId = nodeMatch?.[1] ?? null;
            const failedNodeLabel = failedNodeId
              ? (() => {
                  const n = (doc?.nodes || []).find((nn) => nn.id === failedNodeId);
                  return (n?.ui?.label as string | undefined) || n?.step || failedNodeId;
                })()
              : null;
            // Pull the first sentence (up to ":" or newline) as the
            // headline; the full error stays visible in the <details>.
            // Round-4 UX#3: previously the headline was a hard 200-char
            // cut with no ellipsis — visible truncations looked like
            // bugs. Append "…" when we actually truncated.
            const firstSentence = run.error.split(/[\n:]/)[0];
            const headline = firstSentence.length > 200
              ? firstSentence.slice(0, 197) + "…"
              : firstSentence;
            return (
              <section className={`rounded-xl border p-4 ${m.bg} border-rose-300/40 dark:border-rose-900/60`}>
                <div className="flex items-start justify-between gap-3 mb-2">
                  <p className="text-[10px] uppercase tracking-widest text-rose-700 dark:text-rose-300">
                    ❌ Run failed
                  </p>
                  <div className="flex items-center gap-2">
                    {failedNodeId && doc && (
                      <Link
                        href={`/pipelines/${run.pipelineId}?focus=${failedNodeId}`}
                        className="text-[11px] px-2 py-1 rounded border border-rose-300/60 dark:border-rose-700/60 text-rose-800 dark:text-rose-200 hover:bg-rose-100/60 dark:hover:bg-rose-950/40"
                      >
                        🔍 Open {failedNodeLabel} in editor
                      </Link>
                    )}
                    {/* Was a <Link> to the editor — it navigated and ran
                        nothing, while the page's own copy promised a "Re-run
                        pipeline action". Actually start the run. */}
                    <button
                      onClick={() => rerun.mutate()}
                      disabled={rerun.isPending}
                      className="text-[11px] px-2 py-1 rounded border border-rose-300/60 dark:border-rose-700/60 text-rose-800 dark:text-rose-200 hover:bg-rose-100/60 dark:hover:bg-rose-950/40 disabled:opacity-50"
                    >
                      {rerun.isPending ? "Starting…" : "▶ Re-run pipeline"}
                    </button>
                  </div>
                </div>
                <p className="text-sm font-medium text-rose-900 dark:text-rose-100 mb-2">{headline}</p>
                {failedNodeId && (
                  <p className="text-[11px] text-rose-700 dark:text-rose-300 mb-2">
                    Failing node: <code className="font-mono">{failedNodeId}</code>
                    {failedNodeLabel && failedNodeLabel !== failedNodeId && <> · {failedNodeLabel}</>}
                  </p>
                )}
                <details className="mt-2">
                  <summary className="text-[11px] cursor-pointer text-rose-700 dark:text-rose-300 select-none">
                    Show full error
                  </summary>
                  <pre className="text-xs whitespace-pre-wrap font-mono text-rose-900 dark:text-rose-100 mt-2 overflow-x-auto">{run.error}</pre>
                </details>
              </section>
            );
          })()}

          {/* Inputs — dataset references the run consumed */}
          {doc?.datasets && doc.datasets.length > 0 && (
            <section>
              <h2 className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2 font-mono flex items-center gap-2">
                <span aria-hidden>📥</span>
                Inputs ({doc.datasets.length})
                <span className="text-muted-foreground/60 normal-case font-sans tracking-normal">
                  — datasets the run consumed
                </span>
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {doc.datasets.map((d) => (
                  <Link
                    key={d.id}
                    href={`/datasets/${d.id}`}
                    className="rounded-lg border border-border bg-card hover:bg-muted/30 transition-colors p-3 block"
                  >
                    <div className="flex items-center gap-2">
                      <span aria-hidden>📊</span>
                      <span className="font-medium text-sm">{d.label || d.id}</span>
                    </div>
                    {d.connector && (
                      <p className="text-[10px] text-muted-foreground mt-1 font-mono">{d.connector}</p>
                    )}
                    {d.uri && (
                      <p className="text-[10px] text-muted-foreground/70 mt-0.5 font-mono truncate" title={d.uri}>
                        {d.uri}
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Outputs — parquet snapshots + sink writes */}
          <section>
            <h2 className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2 font-mono flex items-center gap-2">
              <span aria-hidden>📤</span>
              Outputs ({run.outputPaths?.length ?? 0})
              <span className="text-muted-foreground/60 normal-case font-sans tracking-normal">
                — what this run produced
              </span>
            </h2>
            {run.outputPaths && run.outputPaths.length > 0 ? (
              <div className="space-y-3">
                {run.outputPaths.map((path, idx) => {
                  // Match the path back to the OutputSpec via filename:
                  // path looks like `…/runs/<run_id>/<output_name>.parquet`,
                  // and OutputSpec.name appears in the filename.
                  const filename = path.split("/").pop() ?? path;
                  const outputName = filename.replace(/\.parquet$/, "");
                  const spec = doc?.outputs?.find((o) => o.name === outputName);
                  const terminalNodeId = spec?.from?.ref;
                  const nm = terminalNodeId
                    ? ((run.nodeMetrics as Record<string, NodeMetric> | undefined)?.[terminalNodeId])
                    : undefined;
                  return (
                    <OutputCard
                      key={`${path}-${idx}`}
                      uri={`file://${path}`}
                      filename={filename}
                      runId={run.id}
                      outputId={spec?.id}
                      schema={nm?.columns ?? []}
                      rowCount={nm?.rows_out ?? null}
                    />
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground italic">No outputs were produced.</p>
            )}
          </section>

          {/* Per-node timeline */}
          {run.nodeMetrics && Object.keys(run.nodeMetrics).length > 0 && (
            <section>
              <h2 className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2 font-mono flex items-center gap-2">
                <span aria-hidden>🛤</span>
                Per-node timeline ({Object.keys(run.nodeMetrics).length})
                <span className="text-muted-foreground/60 normal-case font-sans tracking-normal">
                  — every step that ran, with metrics + schema
                </span>
              </h2>
              <NodeTimeline
                nodeMetrics={run.nodeMetrics as Record<string, NodeMetric>}
                doc={doc ?? undefined}
                runDurationMs={durationMs}
                runStartedMs={startedMs}
              />
            </section>
          )}

          {/* Artifacts — validation rows, sink writes, intermediates */}
          {run.artifacts && Object.keys(run.artifacts).length > 0 && (
            <section>
              <h2 className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2 font-mono flex items-center gap-2">
                <span aria-hidden>📦</span>
                Artifacts ({Object.values(run.artifacts).flat().length})
                <span className="text-muted-foreground/60 normal-case font-sans tracking-normal">
                  — validation rows, sink writes, intermediate snapshots
                </span>
              </h2>
              <div className="space-y-2">
                {Object.entries(run.artifacts).map(([key, items], i) => (
                  <ArtifactGroup
                    key={key}
                    groupKey={key}
                    items={items}
                    runId={runId}
                    // Round-6 UX#3: pass the doc's outputs so the group
                    // can render the human-readable OutputSpec name
                    // (e.g. "listings_map") instead of leaking the
                    // raw output_id ULID.
                    outputs={doc?.outputs}
                    // Round-9 fix: open only the first 2 groups by
                    // default. Previously every group was open which
                    // force-rendered N nested fetches simultaneously
                    // and defeated the IntersectionObserver lazy-load.
                    defaultOpen={i < 2}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
        {/* Round-6 UX#3: back-to-top FAB on long runs. Threshold of
            720px window scroll inside the container is roughly two
            viewports, when the user has reasonably committed to
            scrolling and might want to jump up. */}
        <BackToTop containerId="run-scroll" />
      </div>
    </main>
  );
}

function BackToTop({ containerId }: { containerId: string }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = document.getElementById(containerId);
    if (!el) return;
    const onScroll = () => setVisible(el.scrollTop > 720);
    el.addEventListener("scroll", onScroll);
    onScroll();
    return () => el.removeEventListener("scroll", onScroll);
  }, [containerId]);
  if (!visible) return null;
  // Round-9 fix: honor prefers-reduced-motion for both the smooth-scroll
  // animation AND the hover:scale transform.
  const reduceMotion = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return (
    <button
      type="button"
      onClick={() => {
        const el = document.getElementById(containerId);
        el?.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
      }}
      title="Back to top"
      aria-label="Scroll back to top"
      className={`fixed bottom-6 right-6 z-30 h-10 w-10 rounded-full bg-emerald-500 hover:bg-emerald-400 text-emerald-950 shadow-lg flex items-center justify-center transition-transform ${reduceMotion ? "" : "hover:scale-105"}`}
    >
      <span aria-hidden className="text-lg">↑</span>
    </button>
  );
}

// ---- Subcomponents -----------------------------------------------------

function Stat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">{label}</div>
      <div className={`text-sm font-medium mt-0.5 ${mono ? "tabular-nums font-mono" : ""}`}>{value}</div>
    </div>
  );
}

function OutputCard({
  uri, filename, runId, outputId, schema, rowCount,
}: {
  uri: string;
  filename: string;
  runId: string;
  outputId?: string;
  schema: string[];
  rowCount: number | null;
}) {
  const [previewOpen, setPreviewOpen] = useMemoState(false);
  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="px-4 py-3 flex items-center gap-3">
        <span aria-hidden className="text-base">📤</span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate">{filename}</p>
          <p className="text-[10px] text-muted-foreground font-mono truncate" title={uri}>{uri}</p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground tabular-nums">
          {rowCount != null && <span>{fmtInt(rowCount)} rows</span>}
          <span>·</span>
          <span>{schema.length} cols</span>
        </div>
        {outputId && (
          <button
            type="button"
            onClick={() => setPreviewOpen((v) => !v)}
            className="text-[11px] px-2 py-0.5 rounded border border-border bg-muted/30 hover:bg-muted transition-colors"
          >
            {previewOpen ? "Hide preview" : "Preview rows"}
          </button>
        )}
      </div>
      {schema.length > 0 && (
        <div className="px-4 pb-3 flex flex-wrap gap-1">
          {schema.map((c) => (
            <span
              key={c}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground font-mono"
            >
              {c}
            </span>
          ))}
        </div>
      )}
      {previewOpen && outputId && (
        <PreviewRows runId={runId} outputId={outputId} />
      )}
    </div>
  );
}

// Tiny useState wrapper. Originally there was a second `import { useState
// as useStateImpl } from "react"` floating below this function that both
// duplicated the top-of-file React import AND violated tsc's "imports
// must precede declarations" rule. Use the already-imported `useState`
// directly — the renaming was vestigial.
function useMemoState<T>(initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [v, setV] = useState<T>(initial);
  return [v, setV];
}

function PreviewRows({ runId, outputId }: { runId: string; outputId: string }) {
  const q = useQuery({
    queryKey: ["run-output-preview", runId, outputId],
    queryFn: () => api.getRunOutput(runId, 0, 25, outputId),
  });
  if (q.isLoading) {
    return <div className="px-4 py-3 text-xs text-muted-foreground italic border-t border-border">Loading rows…</div>;
  }
  if (q.error) {
    return <div className="px-4 py-3 text-xs text-rose-600 dark:text-rose-400 border-t border-border">Could not load preview</div>;
  }
  const data = q.data;
  if (!data || !data.rows || data.rows.length === 0) {
    return <div className="px-4 py-3 text-xs text-muted-foreground italic border-t border-border">No rows.</div>;
  }
  const cols = (data.columns ?? []).map((c) => c.name);
  return (
    <div className="border-t border-border overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead className="bg-muted/30">
          <tr>
            {cols.map((c) => (
              <th key={c} className="px-3 py-1.5 text-left font-mono font-semibold whitespace-nowrap">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.slice(0, 25).map((r, i) => (
            <tr key={i} className="border-t border-border/40">
              {cols.map((c) => {
                const raw = String((r as Record<string, unknown>)[c] ?? "—");
                const truncated = raw.length > 60;
                return (
                  <td
                    key={c}
                    className="px-3 py-1 whitespace-nowrap font-mono text-muted-foreground"
                    // Round-6 UX#3: ``slice(0, 60)`` used to hide the
                    // tail of long values with no way to see the full
                    // string. The full value lives in the ``title=``
                    // tooltip + a click copies it to the clipboard.
                    title={truncated ? `${raw}\n\n(click to copy)` : raw}
                    onClick={() => {
                      if (!truncated) return;
                      try {
                        navigator.clipboard.writeText(raw);
                        toast.success("Cell value copied");
                      } catch { /* clipboard blocked */ }
                    }}
                    style={truncated ? { cursor: "pointer" } : undefined}
                  >
                    {truncated ? raw.slice(0, 60) + "…" : raw}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {data.totalRows > 25 && (
        <p className="px-3 py-2 text-[10px] text-muted-foreground italic">
          Showing first 25 of {fmtInt(data.totalRows)} rows.
        </p>
      )}
    </div>
  );
}

function NodeTimeline({
  nodeMetrics, doc, runDurationMs, runStartedMs,
}: {
  nodeMetrics: Record<string, NodeMetric>;
  doc: { nodes?: Array<{ id: string; step: string; ui?: { label?: string } }> } | undefined;
  runDurationMs: number | null;
  runStartedMs: number | null;
}) {
  const entries = useMemo(
    () => Object.entries(nodeMetrics).map(([id, nm]) => ({ id, ...nm })),
    [nodeMetrics],
  );

  const labelFor = (id: string): string => {
    const node = doc?.nodes?.find((n) => n.id === id);
    return node?.ui?.label ?? node?.step ?? id;
  };

  // Bar widths are proportional to elapsed_ms / total run duration.
  // Falls back to even widths when run duration is unknown (still
  // running, or no started_at).
  const totalElapsed = entries.reduce(
    (s, e) => s + (typeof e.elapsed_ms === "number" ? e.elapsed_ms : 0),
    0,
  );
  const denom = runDurationMs ?? totalElapsed ?? 1;

  return (
    <div className="rounded-lg border border-border bg-card divide-y divide-border/40">
      {entries.map((nm) => {
        const m = statusMeta(nm.status ?? "succeeded");
        const elapsed = typeof nm.elapsed_ms === "number" ? nm.elapsed_ms : 0;
        const widthPct = denom > 0 ? Math.max(2, Math.min(100, (elapsed / denom) * 100)) : 0;
        return (
          <div key={nm.id} className="px-4 py-2.5">
            <div className="flex items-center gap-3 text-xs">
              <span className={`flex items-center gap-1.5 ${m.tone} font-medium`}>
                <span aria-hidden>{m.emoji}</span>
              </span>
              <span className="font-medium truncate flex-1" title={labelFor(nm.id)}>
                {labelFor(nm.id)}
              </span>
              {nm.rows_out != null && (
                <span className="text-muted-foreground tabular-nums whitespace-nowrap">
                  {fmtInt(nm.rows_out)} rows
                </span>
              )}
              <span className="text-muted-foreground tabular-nums whitespace-nowrap w-[80px] text-right">
                {fmtDuration(elapsed)}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 bg-muted/30 rounded overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${widthPct}%` }}
                transition={{ duration: 0.4, ease: "easeOut" }}
                className={[
                  "h-full",
                  nm.status === "failed"   ? "bg-rose-500" :
                  nm.status === "running"  ? "bg-sky-500"  :
                                             "bg-emerald-500",
                ].join(" ")}
              />
            </div>
            {nm.columns && nm.columns.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[10px] text-muted-foreground hover:text-foreground">
                  Output schema ({nm.columns.length} columns)
                </summary>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {nm.columns.map((c) => (
                    <span
                      key={c}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground font-mono"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              </details>
            )}
            {nm.error && (
              <pre className="mt-2 text-[10px] font-mono text-rose-700 dark:text-rose-300 whitespace-pre-wrap">
                {nm.error}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ArtifactGroup({
  groupKey,
  items,
  runId,
  outputs,
  defaultOpen = false,
}: {
  groupKey: string;
  items: Array<Record<string, unknown>>;
  runId: string;
  outputs?: Array<{ id: string; name: string }>;
  defaultOpen?: boolean;
}) {
  // Keys come in three shapes:
  //   - `output_id` (sink + image artifacts for the matching output)
  //   - `_intermediate:<node_id>` (Polars-step intermediates)
  //   - `_validation:<node_id>` (validation_sql output, e.g. check_data)
  let label = groupKey;
  let emoji = "📦";
  if (groupKey.startsWith("_validation:")) {
    label = `Validation · ${groupKey.replace("_validation:", "")}`;
    emoji = "🧪";
  } else if (groupKey.startsWith("_intermediate:")) {
    label = `Intermediate · ${groupKey.replace("_intermediate:", "")}`;
    emoji = "📁";
  } else {
    // Round-6 UX#3: prefer the OutputSpec's user-chosen name to the
    // raw ULID; fall back to the ULID if the doc no longer carries it.
    const specName = outputs?.find((o) => o.id === groupKey)?.name;
    label = specName ? `Output · ${specName}` : `Output · ${groupKey}`;
    emoji = "📤";
  }
  return (
    <details className="rounded-lg border border-border bg-card" {...(defaultOpen ? { open: true } : {})}>
      <summary className="cursor-pointer px-4 py-2 text-xs flex items-center gap-2">
        <span aria-hidden>{emoji}</span>
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">({items.length})</span>
      </summary>
      <div className="px-4 pb-3 space-y-2">
        {items.map((a, i) => (
          <ArtifactItem key={i} artifact={a} runId={runId} />
        ))}
      </div>
    </details>
  );
}

/**
 * One artifact row. Renders inline when the artifact is an image / map /
 * sink (the high-signal cases); falls back to a JSON-pretty-print for
 * everything else (validation rows, intermediates, custom step outputs).
 *
 * The previous version always rendered `<pre>{JSON.stringify(a)}</pre>` —
 * which meant chart artifacts produced by ``export_to_image`` /
 * ``export_to_map`` (the most common artifact type by far) showed up as a
 * blob of metadata instead of an actual chart. Round-2 QA finding.
 */
function ArtifactItem({
  artifact,
  runId,
}: {
  artifact: Record<string, unknown>;
  runId: string;
}) {
  const kind = String(artifact.kind ?? "");
  const format = String(artifact.format ?? "").toLowerCase();
  const path = typeof artifact.path === "string" ? artifact.path : null;
  const title = typeof artifact.title === "string" ? artifact.title : null;
  const chart = typeof artifact.chart === "string" ? artifact.chart : null;

  // Image / map artifact — render inline.
  if (kind === "image" && path) {
    const _tok = getApiToken();
    const headers: Record<string, string> = _tok
      ? { Authorization: `Bearer ${_tok}` }
      : {};
    const url = `${API_BASE}/runs/${runId}/artifact?path=${encodeURIComponent(path)}`;
    if (format === "html" || format === "htm") {
      // Map / interactive HTML — fetch + iframe srcdoc so the user's
      // bearer token is attached. Same pattern as the live preview.
      return (
        <ArtifactHtmlIframe url={url} headers={headers} title={title || chart || "map"} />
      );
    }
    // PNG / SVG raster.
    return (
      <ArtifactImage url={url} headers={headers} title={title || chart || "chart"} />
    );
  }

  // Sink artifact — show file path + row count.
  if (kind === "sink") {
    const uri = typeof artifact.uri === "string" ? artifact.uri : "";
    const rows = typeof artifact.rows === "number" ? artifact.rows : null;
    return (
      <div className="text-[11px] flex items-center gap-2 bg-muted/30 rounded p-2">
        <span aria-hidden>💾</span>
        <span className="font-mono truncate flex-1" title={uri}>{uri}</span>
        {rows != null && <span className="tabular-nums text-muted-foreground">{rows.toLocaleString()} rows</span>}
      </div>
    );
  }

  // File / validation / unknown — keep the JSON dump as a foldable detail.
  return (
    <pre className="text-[10px] font-mono bg-muted/30 rounded p-2 overflow-x-auto whitespace-pre">
      {JSON.stringify(artifact, null, 2)}
    </pre>
  );
}

/** Render a PNG/SVG artifact via auth-headers fetch → blob → data URL.
 *
 * Lazy-load: only fetches when the artifact scrolls into view. Round-3
 * QA finding: the previous version fetched every artifact eagerly on
 * mount, so a run with N chart artifacts triggered N concurrent
 * auth-headed fetches + N parallel data-URL conversions. With 50+
 * charts the browser tab would stall for several seconds and consume
 * 100s of MB of memory. ``IntersectionObserver`` defers the fetch
 * until the artifact is actually visible.
 */
function ArtifactImage({
  url,
  headers,
  title,
}: {
  url: string;
  headers: Record<string, string>;
  title: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    if (inView || !containerRef.current) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setInView(true);
            obs.disconnect();
            return;
          }
        }
      },
      // Pre-fetch a viewport above + below so scrolling feels instant
      // but we still don't fire 50 fetches for an off-screen list.
      { rootMargin: "200px 0px" },
    );
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [inView]);
  const q = useQuery<string, Error>({
    queryKey: ["run-artifact-image", url],
    queryFn: async () => {
      const res = await fetch(url, { headers });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const blob = await res.blob();
      return await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error ?? new Error("read failed"));
        reader.readAsDataURL(blob);
      });
    },
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    enabled: inView,
  });
  // Always-rendered container so IntersectionObserver has something to
  // watch; the inner content depends on fetch state.
  let inner: React.ReactNode;
  if (!inView) {
    inner = (
      <div className="text-[10px] text-muted-foreground italic px-2 py-6 text-center min-h-[120px] flex items-center justify-center">
        scroll into view to load {title}…
      </div>
    );
  } else if (q.isLoading) {
    inner = <div className="text-[10px] text-muted-foreground italic px-2 py-1">loading {title}…</div>;
  } else if (q.error) {
    inner = <div className="text-[10px] text-destructive px-2 py-1">{title}: {q.error.message}</div>;
  } else if (q.data) {
    inner = (
      <>
        <div className="text-[10px] text-muted-foreground font-mono truncate" title={title}>{title}</div>
        {/* eslint-disable-next-line @next/next/no-img-element -- data URL */}
        <img
          src={q.data}
          alt={title}
          className="max-w-full max-h-[60vh] rounded border border-border dark:border-zinc-700 bg-white object-contain"
        />
      </>
    );
  }
  return (
    <div ref={containerRef} className="bg-muted/20 rounded p-2 flex flex-col items-stretch gap-1">
      {inner}
    </div>
  );
}

/** Render an HTML artifact (e.g. export_to_map output) inside a sandboxed iframe. */
function ArtifactHtmlIframe({
  url,
  headers,
  title,
}: {
  url: string;
  headers: Record<string, string>;
  title: string;
}) {
  const q = useQuery<string, Error>({
    queryKey: ["run-artifact-html", url],
    queryFn: async () => {
      const res = await fetch(url, { headers });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return await res.text();
    },
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
  if (q.isLoading) {
    return <div className="text-[10px] text-muted-foreground italic px-2 py-1">loading {title}…</div>;
  }
  if (q.error) {
    return <div className="text-[10px] text-destructive px-2 py-1">{title}: {q.error.message}</div>;
  }
  if (!q.data) return null;
  return (
    <div className="bg-muted/20 rounded p-2 flex flex-col items-stretch gap-1">
      <div className="text-[10px] text-muted-foreground font-mono truncate" title={title}>{title}</div>
      {/*
        Round-3 regression: this iframe still carried `allow-same-origin`
        even though step-image-preview.tsx had it dropped in rc1 hardening.
        With both `allow-scripts` and `allow-same-origin`, scripts running
        inside the srcDoc share the parent origin (DIG's API origin) and
        can fetch DIG endpoints (auth cookies attached) to exfiltrate
        pipelines, runs, settings — including the AI api_key. The map
        artifact is static HTML/JS produced by `export_to_map` from
        user-controlled column values, so a malicious cell could inject
        a script. Drop `allow-same-origin` so the iframe is treated as a
        unique opaque origin and can't reach back into DIG.
      */}
      <iframe
        title={title}
        srcDoc={q.data}
        sandbox="allow-scripts"
        className="w-full aspect-video min-h-[280px] max-h-[60vh] rounded border border-border bg-white"
      />
    </div>
  );
}

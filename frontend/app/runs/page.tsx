"use client";

/**
 * Phase-A-pro #5 — workspace-wide runs list.
 *
 * Filterable grid of every run across every pipeline. Rows are runs;
 * columns are status / pipeline / triggered-by / started / duration /
 * outputs / row-count / tags.
 *
 * Filter bar: status (multi), tag (multi, intersection), pipeline
 * (single picker), time range (preset + custom). Filters survive in
 * URL params so a "share link" reproduces the filtered view.
 *
 * Data shape from `/runs?…&cursor=…` returns a paginated `RunListPage`.
 * Cursor pagination keeps pages stable as new runs land mid-scroll.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";

import { api, searchApi, type RunListItem } from "@/lib/api/client";
import { fmtDuration, fmtInt } from "@/lib/format-number";
import { useURLState } from "@/lib/use-url-state";
import { useDocumentTitle } from "@/lib/use-document-title";
import { PositiveLoader } from "@/components/positive-loader";

// ---- Helpers -----------------------------------------------------------

const STATUS_META: Record<string, { emoji: string; tone: string; label: string }> = {
  succeeded: { emoji: "✅", tone: "text-emerald-700 dark:text-emerald-300", label: "Succeeded" },
  running:   { emoji: "🌀", tone: "text-sky-700 dark:text-sky-300", label: "Running" },
  failed:    { emoji: "❌", tone: "text-rose-700 dark:text-rose-300", label: "Failed" },
  queued:    { emoji: "⏳", tone: "text-zinc-600 dark:text-zinc-400", label: "Queued" },
  cancelled: { emoji: "🛑", tone: "text-zinc-500 dark:text-zinc-400", label: "Cancelled" },
};

function statusMeta(s: string) {
  return STATUS_META[s] ?? { emoji: "❔", tone: "text-zinc-500", label: s };
}

function fmtTimeAgo(iso: string | null): string {
  if (!iso) return "—";
  const stamp = iso.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const t = new Date(stamp).getTime();
  if (Number.isNaN(t)) return "—";
  const diff = Date.now() - t;
  if (diff < 0) return "just now";
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`;
  if (diff < 7 * 86_400_000) return `${Math.round(diff / 86_400_000)}d ago`;
  return new Date(stamp).toLocaleDateString();
}

const TIME_PRESETS = [
  { id: "all",  label: "All time", iso: () => null },
  { id: "1h",   label: "Last 1h",  iso: () => new Date(Date.now() - 3_600_000).toISOString() },
  { id: "24h",  label: "Last 24h", iso: () => new Date(Date.now() - 86_400_000).toISOString() },
  { id: "7d",   label: "Last 7d",  iso: () => new Date(Date.now() - 7 * 86_400_000).toISOString() },
  { id: "30d",  label: "Last 30d", iso: () => new Date(Date.now() - 30 * 86_400_000).toISOString() },
] as const;

const STATUSES = ["succeeded", "running", "failed", "queued", "cancelled"] as const;

// ---- Page --------------------------------------------------------------

interface FilterState {
  status: string[];
  tag: string[];
  pipeline: string | null;
  preset: string;     // matches TIME_PRESETS.id
}
const DEFAULT_FILTERS: FilterState = {
  status: [],
  tag: [],
  pipeline: null,
  preset: "all",
};

export default function RunsPage() {
  useDocumentTitle('Run history');
  // URL-state for shareable filtered views (synergy with the URL state
  // hook from Phase-A-pro #2).
  const [filters, setFilters] = useURLState<FilterState>("rf", DEFAULT_FILTERS);

  const tagsQ = useQuery({
    queryKey: ["all-tags"],
    queryFn: searchApi.listTags,
    staleTime: 30_000,
  });
  const pipelinesQ = useQuery({
    queryKey: ["pipelines"],
    queryFn: api.listPipelines,
    staleTime: 30_000,
  });

  const startedAfter = useMemo(() => {
    const preset = TIME_PRESETS.find((p) => p.id === filters.preset);
    return preset?.iso() ?? null;
  }, [filters.preset]);

  const runsQ = useInfiniteQuery({
    queryKey: ["runs-list", filters, startedAfter],
    queryFn: ({ pageParam }: { pageParam?: string }) =>
      api.listAllRuns({
        status: filters.status.length ? filters.status.join(",") : undefined,
        tag: filters.tag.length ? filters.tag.join(",") : undefined,
        pipeline_id: filters.pipeline || undefined,
        started_after: startedAfter || undefined,
        cursor: pageParam,
        limit: 50,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const items = useMemo(
    () => (runsQ.data?.pages ?? []).flatMap((p) => p.items),
    [runsQ.data?.pages],
  );

  const toggleStatus = (s: string) =>
    setFilters((p) => ({
      ...p,
      status: p.status.includes(s) ? p.status.filter((x) => x !== s) : [...p.status, s],
    }));
  const toggleTag = (t: string) =>
    setFilters((p) => ({
      ...p,
      tag: p.tag.includes(t) ? p.tag.filter((x) => x !== t) : [...p.tag, t],
    }));

  const filtersActive =
    filters.status.length > 0 ||
    filters.tag.length > 0 ||
    filters.pipeline !== null ||
    filters.preset !== "all";

  return (
    <main id="main" className="flex flex-col h-screen overflow-hidden">
      {/* Header */}
      <header className="px-6 py-3 border-b border-border flex items-center gap-3 shrink-0">
        <Link
          href="/"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          ← Home
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700">·</span>
        <h1 className="text-lg font-semibold tracking-tight flex items-center gap-2">
          <span aria-hidden>📜</span>
          Run history
        </h1>
        <p className="text-xs text-muted-foreground">
          Every executed job across every pipeline.
        </p>
        <span className="flex-1" />
        <span className="text-xs text-muted-foreground tabular-nums">
          {runsQ.isLoading
            ? "loading…"
            : `${items.length} run${items.length === 1 ? "" : "s"}${runsQ.hasNextPage ? "+" : ""}`}
        </span>
      </header>

      {/* Filter bar */}
      <div className="px-6 py-3 border-b border-border/60 bg-muted/15 flex flex-wrap items-center gap-3 text-[11px]">
        <span className="text-muted-foreground font-medium">Status:</span>
        {STATUSES.map((s) => {
          const m = statusMeta(s);
          const active = filters.status.includes(s);
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggleStatus(s)}
              aria-pressed={active}
              className={[
                "px-2 py-0.5 rounded-full border transition-all flex items-center gap-1",
                active
                  ? "bg-card border-foreground/40 shadow-sm text-foreground"
                  : "border-transparent hover:border-border text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              <span aria-hidden>{m.emoji}</span>
              {m.label}
            </button>
          );
        })}

        <span className="w-px self-stretch bg-border mx-1" />

        <span className="text-muted-foreground font-medium">When:</span>
        {TIME_PRESETS.map((p) => {
          const active = filters.preset === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => setFilters((cur) => ({ ...cur, preset: p.id }))}
              aria-pressed={active}
              className={[
                "px-2 py-0.5 rounded-full border transition-all",
                active
                  ? "bg-card border-foreground/40 shadow-sm text-foreground"
                  : "border-transparent hover:border-border text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              {p.label}
            </button>
          );
        })}

        {(tagsQ.data?.tags?.length ?? 0) > 0 && (
          <>
            <span className="w-px self-stretch bg-border mx-1" />
            <span className="text-muted-foreground font-medium">Tag:</span>
            {tagsQ.data!.tags.map((t) => {
              const active = filters.tag.includes(t);
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => toggleTag(t)}
                  aria-pressed={active}
                  className={[
                    "px-2 py-0.5 rounded-full border transition-all",
                    active
                      ? "bg-emerald-100 dark:bg-emerald-900/40 border-emerald-300 text-emerald-900 dark:text-emerald-100 font-semibold"
                      : "border-transparent hover:border-border text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  #{t}
                </button>
              );
            })}
          </>
        )}

        <span className="w-px self-stretch bg-border mx-1" />

        <select
          aria-label="Filter by pipeline"
          value={filters.pipeline ?? ""}
          onChange={(e) =>
            setFilters((p) => ({ ...p, pipeline: e.target.value || null }))
          }
          className="text-[11px] bg-card border border-border rounded px-2 py-0.5 outline-none focus:border-foreground/40"
        >
          <option value="">All pipelines</option>
          {(pipelinesQ.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        {filtersActive && (
          <button
            type="button"
            onClick={() => setFilters(DEFAULT_FILTERS)}
            className="ml-auto text-[10px] text-muted-foreground hover:text-foreground underline underline-offset-2"
          >
            clear all
          </button>
        )}
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto">
        {runsQ.isLoading ? (
          <div className="h-full grid place-items-center">
            <PositiveLoader variant="rendering" primary="Loading runs…" size="md" showTimer={false} />
          </div>
        ) : items.length === 0 ? (
          <div className="h-full grid place-items-center text-center text-muted-foreground">
            <div>
              <div className="text-5xl mb-3" aria-hidden>📭</div>
              <p className="text-sm">
                No runs match these filters.
                {filtersActive && (
                  <>
                    {" "}<button
                      onClick={() => setFilters(DEFAULT_FILTERS)}
                      className="underline underline-offset-2 hover:text-foreground"
                    >
                      Clear filters
                    </button>
                  </>
                )}
              </p>
              <p className="text-xs mt-1">Open a pipeline and click <span className="font-mono">▶ Run</span> to populate this list.</p>
              {!filtersActive && (
                <div className="pt-3">
                  <Link
                    href="/pipelines"
                    className="inline-block px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs"
                  >
                    🛤 Browse pipelines
                  </Link>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-xs">
              <thead className="sticky top-0 bg-background/95 backdrop-blur border-b border-border z-10">
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
                  <th className="px-4 py-2 w-[120px]">Status</th>
                  <th className="px-4 py-2">Pipeline</th>
                  <th className="px-4 py-2 w-[110px]">Triggered</th>
                  <th className="px-4 py-2 w-[110px] text-right">Started</th>
                  <th className="px-4 py-2 w-[90px] text-right">Duration</th>
                  <th className="px-4 py-2 w-[70px] text-right">Outputs</th>
                  <th className="px-4 py-2 w-[100px] text-right">Rows</th>
                  <th className="px-4 py-2 w-[140px]">Tags</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <RunRow key={r.id} run={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {runsQ.hasNextPage && (
          <div className="p-4 grid place-items-center" aria-live="polite">
            <button
              type="button"
              onClick={() => runsQ.fetchNextPage()}
              disabled={runsQ.isFetchingNextPage}
              aria-busy={runsQ.isFetchingNextPage}
              className="text-xs px-3 py-1.5 rounded border border-border bg-card hover:bg-muted disabled:opacity-50 transition-colors"
            >
              {runsQ.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </div>
    </main>
  );
}

// ---- Row component -----------------------------------------------------

function RunRow({ run }: { run: RunListItem }) {
  const m = statusMeta(run.status);
  return (
    <motion.tr
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="border-b border-border/40 hover:bg-muted/40 transition-colors"
    >
      <td className="px-4 py-2">
        <Link
          href={`/runs/${run.id}`}
          className={`flex items-center gap-1.5 ${m.tone} font-medium hover:underline underline-offset-2`}
        >
          <span aria-hidden>{m.emoji}</span>
          {m.label}
        </Link>
      </td>
      <td className="px-4 py-2 min-w-0">
        <Link
          href={`/runs/${run.id}`}
          className="hover:underline underline-offset-2 truncate block max-w-[40ch]"
          title={run.pipelineName ?? run.pipelineId}
        >
          {run.pipelineName ?? run.pipelineId}
        </Link>
      </td>
      <td className="px-4 py-2 text-muted-foreground">{run.triggeredBy}</td>
      <td
        className="px-4 py-2 text-right tabular-nums text-muted-foreground"
        title={(() => {
          const t = run.startedAt ?? run.createdAt;
          if (!t) return "";
          const d = new Date(t);
          return Number.isNaN(d.getTime()) ? t : d.toLocaleString();
        })()}
      >
        {fmtTimeAgo(run.startedAt ?? run.createdAt)}
      </td>
      <td className="px-4 py-2 text-right tabular-nums">{fmtDuration(run.durationMs)}</td>
      <td className="px-4 py-2 text-right tabular-nums">{run.outputCount}</td>
      <td className="px-4 py-2 text-right tabular-nums">{run.rowCountTotal != null ? fmtInt(run.rowCountTotal) : "—"}</td>
      <td className="px-4 py-2">
        <div className="flex flex-wrap gap-1">
          {run.pipelineTags.slice(0, 3).map((t) => (
            <span
              key={t}
              className="text-[9px] px-1.5 py-0 rounded-full bg-muted text-muted-foreground"
            >
              #{t}
            </span>
          ))}
          {run.pipelineTags.length > 3 && (
            <span className="text-[9px] text-muted-foreground/70">
              +{run.pipelineTags.length - 3}
            </span>
          )}
        </div>
      </td>
    </motion.tr>
  );
}

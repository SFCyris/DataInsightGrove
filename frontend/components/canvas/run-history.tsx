"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type RunOut } from "@/lib/api/client";
import { humanizeSqlError } from "@/lib/humanize-sql-error";
import { PositiveLoaderInline } from "@/components/positive-loader";
import { fmtDuration } from "@/lib/format-number";

const STATUS_EMOJI: Record<string, string> = {
  succeeded: "✅", failed: "❌", running: "⏳", queued: "🟡",
};

interface Props {
  pipelineId: string;
  /** Refresh trigger — bump after each run start so the latest appears immediately. */
  refreshKey: number;
  /** Open a run's output (called when user clicks a row). */
  onView?: (run: RunOut) => void;
}

// `nowMs` is passed in (not read from Date.now() at call time) so the
// function is pure and SSR-stable. The caller manages the clock via a
// useEffect-backed state — see useNowMs() below. Without this, server
// would render one timestamp string and the client another, triggering
// a hydration mismatch warning on every "Xs ago" cell.
function timeAgo(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return "—";
  if (nowMs === 0) return "—";  // SSR / pre-mount: render a stable placeholder
  const d = new Date(iso);
  const sec = Math.max(0, Math.round((nowMs - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h ago`;
  const day = Math.round(h / 24);
  return `${day}d ago`;
}

/** Current epoch-ms, refreshed every 30s. SSR returns 0 so render output
 *  is stable across server + first client paint; the "real" time appears
 *  after mount via the effect. */
function useNowMs(intervalMs = 30_000): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

function duration(start?: string | null, end?: string | null): string {
  if (!start || !end) return "";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return fmtDuration(ms);
}

export function RunHistory({ pipelineId, refreshKey, onView }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const nowMs = useNowMs();
  const runs = useQuery({
    queryKey: ["runs", pipelineId, refreshKey],
    queryFn: () => api.listRuns(pipelineId),
    // Only poll while the panel is open AND there's a non-terminal run
    // (queued/running). Once everything is in a terminal state nothing's
    // going to change without a user action — drop the timer.
    refetchInterval: (q) => {
      if (!open) return false;
      const data = q.state.data;
      if (!data) return 3000;
      const hasActive = data.some(
        (r) => r.status === "queued" || r.status === "running",
      );
      return hasActive ? 1500 : false;
    },
  });

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const last = runs.data?.[0];
  const lastEmoji = last ? STATUS_EMOJI[last.status] ?? "❔" : "📋";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-muted-foreground hover:text-foreground border border-border rounded-md px-2 py-1 flex items-center gap-1.5 hover:bg-muted/40 transition-colors"
        title={last ? `Last run: ${last.status}` : "No runs yet"}
      >
        <span aria-hidden>{lastEmoji}</span>
        <span className="tabular-nums">
          {runs.data?.length ?? 0} run{runs.data?.length === 1 ? "" : "s"}
        </span>
        {last?.startedAt && last.finishedAt && (
          <span className="text-muted-foreground/70">· {duration(last.startedAt, last.finishedAt)}</span>
        )}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            className="absolute right-0 top-[calc(100%+4px)] w-[340px] max-h-[400px] overflow-auto z-30 rounded-lg border border-border bg-popover shadow-2xl"
          >
            <header className="px-3 py-2 border-b border-border/60 flex items-center gap-2 text-xs">
              <span aria-hidden>📋</span>
              <span className="font-medium">Run history</span>
              <span className="flex-1" />
              <span className="text-muted-foreground">{runs.data?.length ?? 0} total</span>
            </header>
            {runs.isLoading && (
              <div className="p-4 flex justify-center">
                <PositiveLoaderInline variant="rendering" text="Loading runs…" />
              </div>
            )}
            {runs.data?.length === 0 && (
              <div className="p-6 text-center text-xs text-muted-foreground">
                No runs yet. Click <strong>▶️ Run pipeline</strong> in the toolbar.
              </div>
            )}
            <ul
              role="listbox"
              aria-label="Recent runs"
              className="divide-y divide-border/50"
            >
              {(runs.data ?? []).slice(0, 25).map((r) => {
                // Round-5 W4: ticking duration for in-flight runs so the
                // user can see how long they've been waiting (and whether
                // it's a real stall).
                const liveDuration =
                  (r.status === "queued" || r.status === "running") && r.startedAt
                    ? Math.floor((nowMs - new Date(r.startedAt).getTime()) / 1000)
                    : null;
                return (
                <li key={r.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    onClick={() => {
                      onView?.(r);
                      setOpen(false);
                    }}
                    // Failed runs are CLICKABLE — that's exactly when a
                    // user most needs to open the run, to read the error.
                    // Only queued/running rows are inert (nothing to view yet).
                    disabled={r.status === "queued" || r.status === "running"}
                    className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-muted/50 disabled:opacity-50 disabled:cursor-not-allowed text-xs tabular-nums"
                  >
                    <span aria-hidden className="text-base">{STATUS_EMOJI[r.status] ?? "❔"}</span>
                    {/* All children of <button> must be phrasing content (no
                        block-level <p>/<div>/<h*>). React 19 hydration warns
                        on the older <div><p>...</p></div> shape. Stack
                        inline <span>s with `block` instead. */}
                    <span className="min-w-0 flex-1 inline-flex flex-col items-start">
                      <span className="block font-medium truncate">{r.id.slice(-12)}</span>
                      <span className="block text-muted-foreground text-[10px]">
                        {timeAgo(r.createdAt, nowMs)}
                        {r.startedAt && r.finishedAt && ` · ${duration(r.startedAt, r.finishedAt)}`}
                        {liveDuration != null && ` · running ${liveDuration}s`}
                      </span>
                    </span>
                    {r.error && (
                      <span title={r.error} className="text-destructive text-[10px] max-w-[80px] truncate">
                        {humanizeSqlError(r.error, []).title}
                      </span>
                    )}
                  </button>
                </li>
                );
              })}
            </ul>
            {/* Round-5 W4: show a "see all N runs" footer link when the
                popover truncates so the user has a pivot to the full grid. */}
            {(runs.data?.length ?? 0) > 25 && (
              <footer className="px-3 py-2 border-t border-border/60 text-[11px] text-center">
                <Link
                  href={`/runs?pipeline_id=${pipelineId}`}
                  className="text-muted-foreground hover:text-foreground underline"
                  onClick={() => setOpen(false)}
                >
                  See all {runs.data!.length} runs →
                </Link>
              </footer>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

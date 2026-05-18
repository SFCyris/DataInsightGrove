"use client";

/**
 * Settings → Notifications.
 *
 * Append-only log of system + runtime events. Lists newest-first with
 * filter chips (kind, level, include-dismissed) and per-row actions
 * (dismiss, hard-delete). Refreshes via React Query so a freshly-emitted
 * notification (e.g. from a run failure) appears in the list within the
 * page's poll cadence — no full page refresh required.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "motion/react";
import { toast } from "sonner";

import { notificationsApi, type NotificationOut } from "@/lib/api/client";
import { confirmAction } from "@/lib/confirm-toast";
import { PositiveLoaderInline } from "@/components/positive-loader";

const KINDS: { id: string; emoji: string; label: string }[] = [
  { id: "system",     emoji: "🖥️", label: "System" },
  { id: "runtime",    emoji: "⚙️", label: "Runtime" },
  { id: "freshness",  emoji: "⏱",  label: "Freshness" },
  { id: "login",      emoji: "🔑", label: "Login" },
  { id: "resources",  emoji: "💾", label: "Resources" },
  { id: "security",   emoji: "🔐", label: "Security" },
];

const LEVELS = [
  { id: "notification", emoji: "🟢", label: "Notification", tone: "text-emerald-700 dark:text-emerald-300 bg-emerald-50/70 dark:bg-emerald-950/30 border-emerald-200/70 dark:border-emerald-900/50" },
  { id: "warning",      emoji: "🟡", label: "Warning",      tone: "text-amber-700 dark:text-amber-300 bg-amber-50/70 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-900/50" },
  { id: "error",        emoji: "🔴", label: "Error",        tone: "text-rose-700 dark:text-rose-300 bg-rose-50/70 dark:bg-rose-950/30 border-rose-200/70 dark:border-rose-900/50" },
] as const;

function formatLocal(iso: string): string {
  // Backend serializes naive UTC timestamps without a Z; force it so JS
  // parses as UTC (same trick as the canvas's relativeTime).
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  // Round-8 polish: relative time matches the runs page so the inbox
  // feels live ("2m ago") rather than presenting a wall-clock that the
  // operator has to mentally diff. The cell's ``title=`` (set at the
  // call site) carries the absolute UTC value for verification.
  const nowMs = Date.now();
  const sec = Math.max(1, Math.round((nowMs - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 14) return `${day}d ago`;
  // Fall back to ISO date for older items where relative time stops
  // being useful (the title tooltip still shows the precise UTC).
  return d.toLocaleDateString();
}

function formatUtcForTitle(iso: string): string {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`
  );
}

function levelMeta(level: string) {
  return LEVELS.find((l) => l.id === level) ?? LEVELS[0];
}

function kindMeta(kind: string) {
  return KINDS.find((k) => k.id === kind) ?? { id: kind, emoji: "📬", label: kind };
}

export function NotificationsSection() {
  const qc = useQueryClient();
  const [kindFilter, setKindFilter] = useState<string | null>(null);
  const [levelFilter, setLevelFilter] = useState<string | null>(null);
  const [includeDismissed, setIncludeDismissed] = useState(false);

  const listQ = useQuery({
    queryKey: ["notifications", { kindFilter, levelFilter, includeDismissed }],
    queryFn: () =>
      notificationsApi.list({
        kind: kindFilter ?? undefined,
        level: levelFilter ?? undefined,
        includeDismissed,
        limit: 200,
      }),
    // Poll every 10s so newly-emitted events appear without manual refresh.
    refetchInterval: 10_000,
  });

  const dismissM = useMutation({
    mutationFn: (id: string) => notificationsApi.dismiss(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e: Error) => toast.error(`Dismiss failed: ${e.message}`),
  });

  const dismissAllM = useMutation({
    mutationFn: () => notificationsApi.dismissAll(),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      toast.success(`Dismissed ${r.dismissed} notification${r.dismissed === 1 ? "" : "s"}`);
    },
    onError: (e: Error) => toast.error(`Dismiss-all failed: ${e.message}`),
  });

  const removeM = useMutation({
    mutationFn: (id: string) => notificationsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e: Error) => toast.error(`Delete failed: ${e.message}`),
  });

  const items: NotificationOut[] = listQ.data?.items ?? [];
  const unread = listQ.data?.unread ?? 0;

  return (
    <section className="space-y-5">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <span aria-hidden>🔔</span>
          Notifications
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          System + runtime events captured by DIG. Use this as the audit log
          today; future delivery channels (email, syslog, webhook) will read
          from the same store.
        </p>
      </header>

      {/* Filter / action bar */}
      <div className="flex flex-wrap items-center gap-2 border-y border-border py-3">
        <FilterChip
          active={kindFilter === null}
          onClick={() => setKindFilter(null)}
          label="All kinds"
        />
        {KINDS.map((k) => (
          <FilterChip
            key={k.id}
            active={kindFilter === k.id}
            onClick={() => setKindFilter(kindFilter === k.id ? null : k.id)}
            label={`${k.emoji} ${k.label}`}
          />
        ))}
        <span className="mx-1 text-muted-foreground">·</span>
        <FilterChip
          active={levelFilter === null}
          onClick={() => setLevelFilter(null)}
          label="All levels"
        />
        {LEVELS.map((l) => (
          <FilterChip
            key={l.id}
            active={levelFilter === l.id}
            onClick={() => setLevelFilter(levelFilter === l.id ? null : l.id)}
            label={`${l.emoji} ${l.label}`}
          />
        ))}
        <span className="flex-1" />
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={includeDismissed}
            onChange={(e) => setIncludeDismissed(e.target.checked)}
            className="rounded"
          />
          Show dismissed
        </label>
        <button
          type="button"
          onClick={() => dismissAllM.mutate()}
          disabled={unread === 0 || dismissAllM.isPending}
          className="text-xs px-2.5 py-1 rounded border border-border bg-background hover:bg-muted disabled:opacity-50 transition-colors"
        >
          Dismiss all{unread > 0 ? ` (${unread})` : ""}
        </button>
      </div>

      {/* Table */}
      <div
        className="rounded-xl border border-border bg-card/40 overflow-hidden"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Notification inbox"
      >
        <div className="grid grid-cols-[180px_120px_100px_80px_1fr_60px] gap-2 px-4 py-2 text-[10px] uppercase tracking-wide text-muted-foreground font-mono border-b border-border bg-muted/30">
          <div>Date</div>
          <div>Kind</div>
          <div>Level</div>
          <div>User</div>
          <div>Title / Message</div>
          <div className="text-right">Actions</div>
        </div>
        <AnimatePresence initial={false}>
          {listQ.isLoading && (
            <div className="px-4 py-8 flex justify-center">
              <PositiveLoaderInline variant="rendering" text="Loading notifications…" />
            </div>
          )}
          {!listQ.isLoading && items.length === 0 && (
            <div className="px-4 py-12 text-center text-sm text-muted-foreground">
              <span aria-hidden className="text-2xl block mb-2">📭</span>
              No notifications match these filters.
              {!includeDismissed && (
                <span className="block mt-1 text-xs">
                  Try toggling &quot;Show dismissed&quot; to see soft-cleared rows.
                </span>
              )}
            </div>
          )}
          {items.map((n) => {
            const lvl = levelMeta(n.level);
            const kind = kindMeta(n.kind);
            const dimmed = n.dismissedAt != null;
            return (
              <motion.div
                key={n.id}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: dimmed ? 0.55 : 1, y: 0 }}
                exit={{ opacity: 0, height: 0, marginTop: 0, marginBottom: 0 }}
                transition={{ duration: 0.18 }}
                className="grid grid-cols-[180px_120px_100px_80px_1fr_60px] gap-2 px-4 py-2.5 border-b border-border/50 last:border-b-0 text-xs items-start hover:bg-muted/20"
              >
                <div
                  className="font-mono tabular-nums text-muted-foreground"
                  title={formatUtcForTitle(n.createdAt)}
                >
                  {formatLocal(n.createdAt)}
                </div>
                <div>
                  <span className="inline-flex items-center gap-1">
                    <span aria-hidden>{kind.emoji}</span>
                    {kind.label}
                  </span>
                </div>
                <div>
                  <span
                    className={[
                      "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium",
                      lvl.tone,
                    ].join(" ")}
                  >
                    <span aria-hidden>{lvl.emoji}</span>
                    {lvl.label}
                  </span>
                </div>
                <div className="text-muted-foreground italic">
                  {n.userId ?? "N/A"}
                </div>
                <div className="min-w-0">
                  <div className="font-medium truncate flex items-center gap-2" title={n.title}>
                    <span className="truncate">{n.title}</span>
                    {/* Round-5 W4: when an event carries ``run_id`` /
                        ``pipeline_id`` in its context, surface a one-
                        click "Open run" / "Open pipeline" affordance
                        so the user doesn't have to copy IDs out of
                        the foldable JSON below. */}
                    {(() => {
                      const ctx = (n.context ?? {}) as Record<string, unknown>;
                      const runId = typeof ctx.run_id === "string" ? ctx.run_id : null;
                      const pipelineId = typeof ctx.pipeline_id === "string" ? ctx.pipeline_id : null;
                      const links: React.ReactNode[] = [];
                      if (runId) {
                        links.push(
                          <a
                            key="run"
                            href={`/runs/${runId}`}
                            className="text-[10px] text-emerald-700 dark:text-emerald-300 hover:underline shrink-0"
                          >
                            🔍 Run
                          </a>,
                        );
                      }
                      if (pipelineId) {
                        links.push(
                          <a
                            key="pipe"
                            href={`/pipelines/${pipelineId}`}
                            className="text-[10px] text-sky-700 dark:text-sky-300 hover:underline shrink-0"
                          >
                            🛤 Pipeline
                          </a>,
                        );
                      }
                      return links;
                    })()}
                  </div>
                  {n.message && (
                    <div className="text-muted-foreground text-[11px] mt-0.5 leading-snug whitespace-pre-wrap break-words line-clamp-2">
                      {n.message}
                    </div>
                  )}
                  {n.context && Object.keys(n.context).length > 0 && (
                    <details className="mt-1 text-[11px]">
                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground select-none">
                        Context
                      </summary>
                      <pre className="mt-1 px-2 py-1.5 rounded bg-muted/40 overflow-x-auto text-[10px] font-mono">
                        {JSON.stringify(n.context, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
                <div className="flex items-center justify-end gap-1">
                  {n.dismissedAt == null ? (
                    <button
                      type="button"
                      onClick={() => dismissM.mutate(n.id)}
                      title="Dismiss (keeps row in audit log)"
                      aria-label="Dismiss notification"
                      className="text-[10px] px-1.5 py-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <span aria-hidden>✓</span>
                    </button>
                  ) : (
                    <span
                      className="text-[10px] text-muted-foreground italic"
                      title={`Dismissed ${formatUtcForTitle(n.dismissedAt)}`}
                    >
                      dismissed
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={async () => {
                      const ok = await confirmAction({
                        title: "Permanently delete this notification?",
                        description: "The row will be removed from the audit log too.",
                        confirmLabel: "Delete",
                      });
                      if (ok) removeM.mutate(n.id);
                    }}
                    title="Permanently delete"
                    aria-label="Permanently delete notification"
                    className="text-[10px] px-1.5 py-0.5 rounded hover:bg-rose-100 dark:hover:bg-rose-950/40 text-muted-foreground hover:text-rose-600 dark:hover:text-rose-400 transition-colors"
                  >
                    <span aria-hidden>🗑</span>
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      <p className="text-[11px] text-muted-foreground italic">
        Refreshes every 10s. Dismissing soft-clears a row (still in the audit
        log via &quot;Show dismissed&quot;); the trash icon hard-deletes it.
      </p>
    </section>
  );
}

function FilterChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        "text-xs px-2.5 py-1 rounded-full border transition-colors",
        active
          ? "bg-emerald-100 dark:bg-emerald-900/40 border-emerald-300 dark:border-emerald-700 text-emerald-900 dark:text-emerald-100"
          : "bg-background border-border hover:bg-muted text-foreground/80",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

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

function formatUtc(iso: string): string {
  // Backend serializes naive UTC timestamps without a Z; force it so JS
  // parses as UTC (same trick as the canvas's relativeTime).
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  // Compact ISO: "2026-05-08 21:00:18 UTC"
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
      <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
        <div className="grid grid-cols-[180px_120px_100px_80px_1fr_60px] gap-2 px-4 py-2 text-[10px] uppercase tracking-wide text-muted-foreground font-mono border-b border-border bg-muted/30">
          <div>Date (UTC)</div>
          <div>Kind</div>
          <div>Level</div>
          <div>User</div>
          <div>Title / Message</div>
          <div className="text-right">Actions</div>
        </div>
        <AnimatePresence initial={false}>
          {listQ.isLoading && (
            <div className="px-4 py-8 text-sm text-muted-foreground italic">
              Loading…
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
                <div className="font-mono tabular-nums text-muted-foreground">
                  {formatUtc(n.createdAt)}
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
                  <div className="font-medium truncate" title={n.title}>
                    {n.title}
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
                      className="text-[10px] px-1.5 py-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    >
                      ✓
                    </button>
                  ) : (
                    <span
                      className="text-[10px] text-muted-foreground italic"
                      title={`Dismissed ${formatUtc(n.dismissedAt)}`}
                    >
                      dismissed
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm("Permanently delete this notification?")) {
                        removeM.mutate(n.id);
                      }
                    }}
                    title="Permanently delete"
                    className="text-[10px] px-1.5 py-0.5 rounded hover:bg-rose-100 dark:hover:bg-rose-950/40 text-muted-foreground hover:text-rose-600 dark:hover:text-rose-400 transition-colors"
                  >
                    🗑
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

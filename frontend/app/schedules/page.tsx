"use client";

/**
 * Pipeline schedules — thin UI over the existing dig-schedule.sh / crontab
 * setup. Lists every DIG-managed cron entry, lets you add or remove one
 * per pipeline.
 *
 * Backed by the crontab on the host where the backend runs. Schedules
 * survive across DIG restarts but require the host's cron daemon to be
 * running (Linux: usually on by default; macOS: on by default).
 */

import Link from "next/link";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, schedulesApi, ApiError } from "@/lib/api/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { useDocumentTitle } from "@/lib/use-document-title";
import { explainCron, nextFireTime, describeRelative } from "@/lib/cron-explain";
import { PositiveLoaderInline } from "@/components/positive-loader";
import { confirmAction } from "@/lib/confirm-toast";

const PRESETS = [
  { label: "Every 15 min", cron: "*/15 * * * *" },
  { label: "Hourly",       cron: "0 * * * *" },
  { label: "Daily 8am",    cron: "0 8 * * *" },
  { label: "Daily midnight", cron: "0 0 * * *" },
  { label: "Mondays 9am",  cron: "0 9 * * 1" },
];

export default function SchedulesPage() {
  useDocumentTitle('Schedules');
  const reduce = useReducedMotion();
  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 } };

  const qc = useQueryClient();
  const schedules = useQuery({ queryKey: ["schedules"], queryFn: schedulesApi.list });
  const pipelines = useQuery({ queryKey: ["pipelines"], queryFn: api.listPipelines });

  const pipelineById = new Map(
    (pipelines.data ?? []).map((p) => [p.id, p.name ?? p.id]),
  );

  const [pid, setPid] = useState("");
  const [cron, setCron] = useState("0 8 * * *");
  const [sample, setSample] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  const onAdd = async () => {
    if (!pid || !cron.trim()) return;
    setSubmitting(true);
    try {
      await schedulesApi.add(
        pid,
        cron.trim(),
        sample ? Number(sample) : undefined,
      );
      qc.invalidateQueries({ queryKey: ["schedules"] });
      toast.success("Schedule added");
      setPid("");
      setSample("");
      // Round-9 fix: also reset cron back to the default so the form
      // doesn't look "still ready to submit" with stale text after a
      // successful add.
      setCron("0 8 * * *");
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      // Round-4 UX#3: the backend "can never fire" / range error is
      // accurate but reads as raw debug text. Surface a friendlier
      // hint where we can detect the impossible-day case; the raw
      // message still goes via the toast description.
      const friendly = (() => {
        if (/can never fire/i.test(msg)) {
          return "That cron expression can never fire — usually a day/month combination that doesn't exist (e.g. Feb 31). Pick a different day or use one of the presets above.";
        }
        if (/out of range/i.test(msg)) {
          return "One of the cron fields is out of range. Allowed ranges: minute 0–59, hour 0–23, day-of-month 1–31, month 1–12, day-of-week 0–7.";
        }
        return msg;
      })();
      toast.error(friendly, { description: friendly !== msg ? msg : undefined });
    } finally {
      setSubmitting(false);
    }
  };

  const onRemove = async (pipelineId: string) => {
    // Round-9 fix: schedules used to delete on a single click with no
    // confirmation. Match the dataset / pipeline cards' confirm-toast
    // pattern so an accidental click can't silently kill a cron.
    const ok = await confirmAction({
      title: "Remove schedule?",
      description: "Stops the cron entry. The pipeline itself stays — you can re-schedule later.",
      confirmLabel: "Remove",
    });
    if (!ok) return;
    try {
      await schedulesApi.remove(pipelineId);
      qc.invalidateQueries({ queryKey: ["schedules"] });
      toast.success("Schedule removed");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <main id="main" className="flex-1 overflow-y-auto p-6 sm:p-10 max-w-4xl mx-auto w-full">
      <motion.header {...fadeUp} className="mb-6 flex items-center justify-between">
        <div>
          <Link href="/" className="text-xs text-muted-foreground hover:text-foreground">← Home</Link>
          <h1 className="text-2xl font-semibold tracking-tight mt-1">⏰ Pipeline schedules</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Survives DIG restarts. Runs even when the editor is closed —
            requires the host to be on at the scheduled time.
          </p>
        </div>
      </motion.header>

      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-6">
        <h2 className="font-medium">Add a schedule</h2>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_2fr] gap-3">
          <div>
            <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">Pipeline</label>
            <select
              value={pid}
              onChange={(e) => setPid(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-2 py-2 text-sm"
            >
              <option value="">— select —</option>
              {(pipelines.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name ?? p.id} · {p.id.slice(-8)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">
              Cron expression (m h dom mon dow)
            </label>
            <input
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              placeholder="0 8 * * *"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
            />
            {/* Round-6 UX#4: human-readable readback under the cron input
                so the user can confidence-check what `0 8 * * *` means
                before clicking Add — without leaving the page or doing
                mental cron parsing. */}
            {(() => {
              const phrase = explainCron(cron);
              const next = nextFireTime(cron);
              if (!phrase && !next) return null;
              return (
                <div className="mt-1.5 text-[11px] text-muted-foreground leading-snug">
                  {phrase ? <span>📅 Fires {phrase}</span> : null}
                  {next ? (
                    <span className="ml-2 text-emerald-600 dark:text-emerald-400">
                      · next: {describeRelative(next)} ({next.toLocaleString()})
                    </span>
                  ) : null}
                </div>
              );
            })()}
            <div className="flex flex-wrap gap-1 mt-2">
              {PRESETS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => setCron(p.cron)}
                  className="text-[10px] px-2 py-0.5 rounded border border-border hover:bg-muted"
                  title={p.cron}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_2fr] gap-3 sm:items-end">
          <div>
            <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">
              Sample rows (optional)
            </label>
            <input
              type="number"
              value={sample}
              onChange={(e) => setSample(e.target.value)}
              placeholder="all rows"
              min={1}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
            />
            <p className="text-[10px] text-muted-foreground mt-1">
              Leave blank to run on full dataset.
            </p>
          </div>
          <div className="flex justify-end">
            <Button onClick={onAdd} disabled={submitting || !pid || !cron.trim()} size="sm">
              {submitting ? "⏳ Adding…" : "➕ Add schedule"}
            </Button>
          </div>
        </div>
      </motion.section>

      <motion.section {...fadeUp} className="space-y-2">
        <h2 className="font-medium">Active schedules</h2>
        {schedules.isLoading && (
          <PositiveLoaderInline variant="rendering" text="Loading schedules…" />
        )}
        {schedules.data && schedules.data.length === 0 && (
          <div className="rounded-md border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground space-y-2">
            <div className="text-3xl" aria-hidden>⏰</div>
            <p>No schedules yet.</p>
            <p className="text-[11px]">Pick a pipeline below and click <span className="font-mono">➕ Add schedule</span> to start one.</p>
          </div>
        )}
        {(schedules.data ?? []).map((s) => (
          <div
            key={s.pipeline_id}
            className="rounded-md border border-border bg-card p-3 flex items-center gap-3"
          >
            <span className="text-base" aria-hidden>⏰</span>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm truncate">
                {pipelineById.get(s.pipeline_id) ?? s.pipeline_id}
              </p>
              <p className="text-[11px] text-muted-foreground font-mono">
                {s.cron}{s.sample_rows ? ` · sample ${s.sample_rows.toLocaleString("en-US")}` : ""}
              </p>
              {/* Round-6 UX#4: next-fire preview per schedule row. */}
              {(() => {
                const next = nextFireTime(s.cron);
                if (!next) return null;
                return (
                  <p className="text-[11px] text-emerald-600 dark:text-emerald-400">
                    📅 Next: {describeRelative(next)} ({next.toLocaleString()})
                  </p>
                );
              })()}
            </div>
            <Link
              href={`/pipelines/${s.pipeline_id}`}
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              Open
            </Link>
            <Button variant="ghost" size="sm" onClick={() => onRemove(s.pipeline_id)}>
              ✕ Remove
            </Button>
          </div>
        ))}
      </motion.section>
    </main>
  );
}

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

const PRESETS = [
  { label: "Every 15 min", cron: "*/15 * * * *" },
  { label: "Hourly",       cron: "0 * * * *" },
  { label: "Daily 8am",    cron: "0 8 * * *" },
  { label: "Daily midnight", cron: "0 0 * * *" },
  { label: "Mondays 9am",  cron: "0 9 * * 1" },
];

export default function SchedulesPage() {
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
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const onRemove = async (pipelineId: string) => {
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
            Cron-backed. Schedules live in your host's crontab and run via <code className="font-mono text-foreground/80">dig-run.sh</code>.
            Survives DIG restarts; requires the host's cron daemon to be running.
          </p>
        </div>
      </motion.header>

      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-6">
        <h2 className="font-medium">Add a schedule</h2>
        <div className="grid grid-cols-[1fr_2fr] gap-3">
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
        <div className="grid grid-cols-[1fr_2fr] gap-3 items-end">
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
        {schedules.isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {schedules.data && schedules.data.length === 0 && (
          <p className="text-sm text-muted-foreground italic">No schedules yet.</p>
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

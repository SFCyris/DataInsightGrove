"use client";

import { useMemo, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  type PipelineDiffResult,
  type PipelineHistoryEntry,
  type StepDiffEntry,
} from "@/lib/api/client";
import { useExpertise } from "@/lib/settings";

const TRIGGER_LABEL: Record<PipelineHistoryEntry["triggeredBy"], string> = {
  manual_save: "💾 Save",
  run_start: "▶️ Run start",
  import: "📥 Import",
  ai_review_apply: "✨ AI review",
  restore: "↩️ Restore",
};

const KIND_TINT: Record<StepDiffEntry["kind"], string> = {
  added: "border-emerald-400/60 bg-emerald-50/60 dark:bg-emerald-900/20",
  removed: "border-rose-400/60 bg-rose-50/60 dark:bg-rose-900/20",
  param_changed: "border-amber-400/60 bg-amber-50/60 dark:bg-amber-900/20",
  type_changed: "border-violet-400/60 bg-violet-50/60 dark:bg-violet-900/20",
  moved: "border-sky-400/60 bg-sky-50/60 dark:bg-sky-900/20",
  unchanged: "border-border bg-card/60",
};

const KIND_EMOJI: Record<StepDiffEntry["kind"], string> = {
  added: "🟢",
  removed: "🔴",
  param_changed: "🟠",
  type_changed: "🟣",
  moved: "🔵",
  unchanged: "⚪",
};

const KIND_VERB: Record<StepDiffEntry["kind"], string> = {
  added: "Added",
  removed: "Removed",
  param_changed: "Changed",
  type_changed: "Type changed",
  moved: "Moved",
  unchanged: "Unchanged",
};

interface Props {
  pipelineId: string;
  /** Initial "from" reference. "previous" picks the snapshot before current. */
  fromRef?: string;
  toRef?: string;
}

/**
 * Pipeline diff view.
 *
 * Adaptive surface:
 *  - Beginner: unified narrative ("Added X, removed Y, changed Z").
 *  - Builder:  side-by-side step strip with hoverable param diffs.
 *  - Engineer: + raw JSON diff tab + per-snapshot picker.
 */
export function PipelineDiffView({
  pipelineId,
  fromRef = "previous",
  toRef = "current",
}: Props) {
  const reduce = useReducedMotion();
  const { isAtLeast } = useExpertise();
  const [from, setFrom] = useState(fromRef);
  const [to, setTo] = useState(toRef);
  const [tab, setTab] = useState<"summary" | "side-by-side" | "json">(
    isAtLeast("builder") ? "side-by-side" : "summary",
  );

  const historyQ = useQuery({
    queryKey: ["pipeline-history", pipelineId],
    queryFn: () => api.listPipelineHistory(pipelineId, 50),
    staleTime: 30_000,
  });

  const diffQ = useQuery({
    queryKey: ["pipeline-diff", pipelineId, from, to],
    queryFn: () => api.diffPipeline(pipelineId, from, to),
  });

  const fade = reduce
    ? { initial: false as const, animate: { opacity: 1 } }
    : { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.18 } };

  return (
    <div className="flex flex-col h-full min-h-0">
      <header className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/40">
        <span className="text-xl select-none" role="img" aria-label="Compare">↔</span>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold tracking-tight">Pipeline diff</h2>
          {diffQ.data && (
            <p className="text-xs text-muted-foreground tabular-nums">
              {diffQ.data.summary}
              <span className="ml-2 text-[10px] text-muted-foreground/70">
                from <code>{from}</code> to <code>{to}</code>
              </span>
            </p>
          )}
        </div>
        <RefPicker
          label="From"
          value={from}
          onChange={setFrom}
          history={historyQ.data ?? []}
          showAdvanced={isAtLeast("engineer")}
        />
        <RefPicker
          label="To"
          value={to}
          onChange={setTo}
          history={historyQ.data ?? []}
          showAdvanced={isAtLeast("engineer")}
        />
      </header>

      <div className="flex items-center gap-1 px-4 py-2 border-b border-border bg-background/40">
        <TabButton active={tab === "summary"} onClick={() => setTab("summary")}>
          📋 Summary
        </TabButton>
        {isAtLeast("builder") && (
          <TabButton
            active={tab === "side-by-side"}
            onClick={() => setTab("side-by-side")}
          >
            ↔ Side-by-side
          </TabButton>
        )}
        {isAtLeast("engineer") && (
          <TabButton active={tab === "json"} onClick={() => setTab("json")}>
            { } JSON
          </TabButton>
        )}
      </div>

      <motion.div {...fade} className="flex-1 overflow-y-auto p-4">
        {diffQ.isLoading && (
          <p className="text-sm text-muted-foreground">Computing diff…</p>
        )}
        {diffQ.error && (
          <p className="text-sm text-destructive">
            Diff failed: {(diffQ.error as Error).message}
          </p>
        )}
        {diffQ.data && tab === "summary" && (
          <SummaryView diff={diffQ.data} />
        )}
        {diffQ.data && tab === "side-by-side" && (
          <SideBySideView diff={diffQ.data} />
        )}
        {diffQ.data && tab === "json" && (
          <JsonView pipelineId={pipelineId} fromRef={from} toRef={to} />
        )}
      </motion.div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "px-3 py-1 rounded-md text-xs transition-colors",
        active
          ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-200"
          : "text-muted-foreground hover:bg-muted",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function RefPicker({
  label,
  value,
  onChange,
  history,
  showAdvanced,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  history: PipelineHistoryEntry[];
  showAdvanced: boolean;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">{label}:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-background px-2 py-1 text-xs"
      >
        <option value="current">📌 Current (live)</option>
        <option value="previous">⏮ Previous snapshot</option>
        {showAdvanced &&
          history.map((h) => (
            <option key={h.id} value={h.id}>
              {TRIGGER_LABEL[h.triggeredBy] ?? "·"} ·{" "}
              {new Date(h.createdAt).toLocaleString()}
            </option>
          ))}
      </select>
    </label>
  );
}

// ---- Summary view (Beginner) --------------------------------------------

function SummaryView({ diff }: { diff: PipelineDiffResult }) {
  const groups = useMemo(() => {
    const out: Record<string, StepDiffEntry[]> = {};
    for (const s of diff.steps) {
      if (s.kind === "unchanged") continue;
      (out[s.kind] ||= []).push(s);
    }
    return out;
  }, [diff]);

  const order: StepDiffEntry["kind"][] = [
    "added",
    "removed",
    "type_changed",
    "param_changed",
    "moved",
  ];

  if (order.every((k) => !groups[k]?.length) && diff.datasets.every((d) => d.kind === "unchanged") && diff.outputs.every((o) => o.kind === "unchanged")) {
    return (
      <div className="text-center py-12">
        <span className="text-5xl select-none" aria-hidden>🟰</span>
        <p className="mt-3 text-sm text-muted-foreground">
          No structural changes between these two versions.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {order.map((kind) => {
        const items = groups[kind];
        if (!items?.length) return null;
        return (
          <section key={kind}>
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-widest mb-2 flex items-center gap-1.5">
              <span aria-hidden>{KIND_EMOJI[kind]}</span>
              {KIND_VERB[kind]} ({items.length})
            </h3>
            <ul className="space-y-2">
              {items.map((s) => (
                <li
                  key={s.node_id}
                  className={[
                    "rounded-lg border px-3 py-2 text-sm",
                    KIND_TINT[s.kind],
                  ].join(" ")}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium truncate">{s.label}</span>
                    <span className="text-[10px] font-mono text-muted-foreground">
                      {s.node_id.slice(-8)}
                    </span>
                  </div>
                  {s.param_changes.length > 0 && (
                    <ul className="mt-1.5 space-y-0.5 text-xs">
                      {s.param_changes.map((p) => (
                        <li key={p.key} className="flex items-center gap-1.5">
                          <code className="text-muted-foreground">{p.key}</code>
                          <span className="text-muted-foreground/70">
                            {p.a_summary}
                          </span>
                          <span aria-hidden>→</span>
                          <span className="text-foreground">{p.b_summary}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {(diff.datasets.some((d) => d.kind !== "unchanged") ||
        diff.outputs.some((o) => o.kind !== "unchanged")) && (
        <section>
          <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-widest mb-2">
            📁 Datasets &amp; outputs
          </h3>
          <ul className="space-y-1 text-xs">
            {diff.datasets
              .filter((d) => d.kind !== "unchanged")
              .map((d) => (
                <li key={d.dataset_id}>
                  <span aria-hidden>
                    {d.kind === "added" ? "🟢" : d.kind === "removed" ? "🔴" : "🟠"}
                  </span>{" "}
                  Dataset <code>{d.label}</code>: {d.kind.replace("_", " ")}
                </li>
              ))}
            {diff.outputs
              .filter((o) => o.kind !== "unchanged")
              .map((o) => (
                <li key={o.output_id}>
                  <span aria-hidden>
                    {o.kind === "added" ? "🟢" : o.kind === "removed" ? "🔴" : "🟠"}
                  </span>{" "}
                  Output <code>{o.name}</code>: {o.kind.replace("_", " ")}
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ---- Side-by-side view (Builder) ----------------------------------------

function SideBySideView({ diff }: { diff: PipelineDiffResult }) {
  // Build two rendered sequences keyed by position.
  const aSteps = [...diff.steps].sort(
    (s1, s2) => (s1.a_position ?? 999) - (s2.a_position ?? 999),
  );
  const bSteps = [...diff.steps].sort(
    (s1, s2) => (s1.b_position ?? 999) - (s2.b_position ?? 999),
  );
  return (
    <div className="grid grid-cols-2 gap-4">
      <Pane title="From" steps={aSteps.filter((s) => s.a_position != null)} side="a" />
      <Pane title="To" steps={bSteps.filter((s) => s.b_position != null)} side="b" />
    </div>
  );
}

function Pane({
  title,
  steps,
  side,
}: {
  title: string;
  steps: StepDiffEntry[];
  side: "a" | "b";
}) {
  return (
    <div>
      <h4 className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
        {title}
      </h4>
      <ol className="space-y-1.5">
        {steps.map((s, i) => {
          const visualKind: StepDiffEntry["kind"] =
            (side === "a" && s.kind === "added") ? "unchanged" :
            (side === "b" && s.kind === "removed") ? "unchanged" :
            s.kind;
          return (
            <li
              key={`${side}-${s.node_id}-${i}`}
              className={[
                "rounded-md border px-2.5 py-1.5 text-xs",
                KIND_TINT[visualKind],
              ].join(" ")}
              title={s.param_changes.map((p) => `${p.key}: ${p.a_summary} → ${p.b_summary}`).join("\n")}
            >
              <div className="flex items-center gap-1.5">
                <span aria-hidden>{KIND_EMOJI[s.kind]}</span>
                <span className="truncate flex-1">{s.label}</span>
                <span className="text-[10px] font-mono text-muted-foreground">
                  #{(side === "a" ? s.a_position : s.b_position) ?? "—"}
                </span>
              </div>
              {s.param_changes.length > 0 && (
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  {s.param_changes.length} param change
                  {s.param_changes.length === 1 ? "" : "s"}
                </p>
              )}
            </li>
          );
        })}
        {steps.length === 0 && (
          <li className="text-xs text-muted-foreground italic">
            (empty)
          </li>
        )}
      </ol>
    </div>
  );
}

// ---- JSON view (Engineer) -----------------------------------------------

function JsonView({
  pipelineId,
  fromRef,
  toRef,
}: {
  pipelineId: string;
  fromRef: string;
  toRef: string;
}) {
  const aQ = useQuery({
    queryKey: ["pipeline-doc", pipelineId, fromRef],
    queryFn: () => fetchDocByRef(pipelineId, fromRef),
  });
  const bQ = useQuery({
    queryKey: ["pipeline-doc", pipelineId, toRef],
    queryFn: () => fetchDocByRef(pipelineId, toRef),
  });
  return (
    <div className="grid grid-cols-2 gap-3 text-xs">
      <pre className="rounded border border-border bg-card/40 p-2 overflow-auto max-h-[600px] tabular-nums">
        {aQ.data ? JSON.stringify(aQ.data, null, 2) : "—"}
      </pre>
      <pre className="rounded border border-border bg-card/40 p-2 overflow-auto max-h-[600px] tabular-nums">
        {bQ.data ? JSON.stringify(bQ.data, null, 2) : "—"}
      </pre>
    </div>
  );
}

async function fetchDocByRef(pipelineId: string, ref: string): Promise<unknown> {
  if (ref === "current") {
    const p = await api.getPipeline(pipelineId);
    return p.document;
  }
  if (ref === "previous") {
    const hist = await api.listPipelineHistory(pipelineId, 1);
    if (hist.length === 0) return null;
    const snap = await api.getPipelineSnapshot(pipelineId, hist[0].id);
    return snap.document;
  }
  if (ref.startsWith("run:")) {
    // Find the run-start snapshot for this run via the history list.
    // The summary/side-by-side panes already resolve `run:` server-side;
    // the JSON tab just needs the matching document.
    const runId = ref.slice("run:".length);
    const hist = await api.listPipelineHistory(pipelineId, 50);
    const match = hist.find(
      (h) => h.triggeredBy === "run_start" && h.runId === runId,
    );
    if (!match) return null;
    const snap = await api.getPipelineSnapshot(pipelineId, match.id);
    return snap.document;
  }
  const snap = await api.getPipelineSnapshot(pipelineId, ref);
  return snap.document;
}

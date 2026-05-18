"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type StepManifest } from "@/lib/api/client";
import { evaluateRequirements, unmetTooltip } from "@/lib/step-requirements";
import { rankSteps } from "@/lib/step-search";
import { AiRibbon } from "./ai-ribbon";
import { CATEGORY_EMOJI } from "@/lib/category-emoji";

// Render order is fixed below so the picker has a predictable visual
// hierarchy regardless of which categories happen to have matches in a
// given query.

const CATEGORY_ORDER: string[] = [
  "clean", "shape", "derive", "aggregate", "combine",
  "analyze", "model", "validate", "visualize",
  "ingest", "output", "custom",
];

interface Props {
  open: boolean;
  onClose: () => void;
  /**
   * Drop the chosen step into the pipeline. The optional `paramsOverride`
   * lets callers (the AI ribbon) inject pre-filled params instead of
   * defaults — typical use: `onPick(manifest, { column: "email" })`.
   */
  onPick: (step: StepManifest, paramsOverride?: Record<string, unknown>) => void;
  /** Anchor element rect (in viewport coords) — popover positions just above it. */
  anchor: { x: number; y: number; w: number; h: number } | null;
  /**
   * Schema of the upstream node (column-name → logical-type-id). Used to
   * grey out steps whose `requires` clauses aren't satisfied by what's
   * available. Pass `{}` (or omit) when there's no upstream — every step
   * stays enabled in that case.
   */
  upstreamSchema?: Record<string, string>;
  /** Pipeline + focused node — required for the AI ribbon. Omit either
   *  and the ribbon stays hidden. */
  pipelineId?: string;
  focusedNodeId?: string | null;
}

// localStorage key for the recently-picked step list (capped at 6).
const RECENT_KEY = "dig.quickadd.recent.v1";
const RECENT_MAX = 6;

function readRecent(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch { return []; }
}
function writeRecent(stepId: string) {
  if (typeof window === "undefined") return;
  const cur = readRecent().filter((s) => s !== stepId);
  cur.unshift(stepId);
  window.localStorage.setItem(RECENT_KEY, JSON.stringify(cur.slice(0, RECENT_MAX)));
}

export function QuickAddMenu({
  open, onClose, onPick, anchor, upstreamSchema, pipelineId, focusedNodeId,
}: Props) {
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const ref = useRef<HTMLDivElement>(null);

  const stepsQ = useQuery({ queryKey: ["steps"], queryFn: api.listSteps, staleTime: 60_000 });

  // Per-step requirement evaluation against the upstream schema. The map
  // is keyed by step id so the render path is a cheap lookup. Memoized
  // on the schema reference + the step list so it only recomputes when
  // either changes (schema is rebuilt on every preview, but the object
  // identity is stable per render of the parent).
  const reqsByStep = useMemo(() => {
    const out: Record<string, ReturnType<typeof evaluateRequirements>> = {};
    for (const s of stepsQ.data ?? []) {
      out[s.id] = evaluateRequirements(s.requires, upstreamSchema);
    }
    return out;
  }, [stepsQ.data, upstreamSchema]);

  // Reload recent list each time the menu opens (cheap; no storage event listener).
  useEffect(() => {
    if (open) setRecent(readRecent());
  }, [open]);

  // Wrap onPick so we record usage. Defined here so anywhere that calls it
  // benefits — including the Enter-to-pick path below and the AI ribbon's
  // suggestion-card click.
  const handlePick = (s: StepManifest, paramsOverride?: Record<string, unknown>) => {
    writeRecent(s.id);
    onPick(s, paramsOverride);
  };

  useEffect(() => {
    if (open) {
      // Round-5 W1 finding: previously reset to empty on every open.
      // Persist the last query in sessionStorage so closing the popover
      // to look at a step, then reopening, keeps the user's typed
      // filter — a common back-and-forth comparison workflow.
      try {
        const persisted = window.sessionStorage.getItem("dig.quickadd.query");
        if (persisted) setQuery(persisted);
      } catch { /* ignore */ }
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    try {
      window.sessionStorage.setItem("dig.quickadd.query", query);
    } catch { /* ignore */ }
  }, [open, query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open, onClose]);

  // Intent ranker: fed the full catalog + recency + req results, returns
  // the matching steps sorted by score. With an empty query we keep the
  // full list (sorted only by recency boost — the visual layout is
  // category-grouped below).
  const filtered = useMemo(() => {
    const ranked = rankSteps({
      steps: stepsQ.data ?? [],
      query,
      recent,
      reqsByStep,
    });
    return ranked.map((r) => r.step);
  }, [query, stepsQ.data, recent, reqsByStep]);

  // Group + render in the fixed CATEGORY_ORDER. When query is empty the
  // grouped layout is the natural visual hierarchy. When the user has
  // typed, we show a flat ranked list instead — categories add noise
  // when ranking is the meaningful signal.
  const grouped = useMemo(() => {
    if (query.trim()) return null;
    const out: Record<string, StepManifest[]> = {};
    for (const s of filtered) (out[s.category] ||= []).push(s);
    // Sort categories by the canonical order; unknown categories drop
    // to the end in the order they appeared.
    const ordered: [string, StepManifest[]][] = [];
    for (const cat of CATEGORY_ORDER) {
      if (out[cat]) ordered.push([cat, out[cat]]);
    }
    for (const [cat, items] of Object.entries(out)) {
      if (!CATEGORY_ORDER.includes(cat)) ordered.push([cat, items]);
    }
    return ordered;
  }, [filtered, query]);

  if (!open || !anchor) return null;

  const w = 320;
  const h = 360;
  let x = anchor.x;
  let y = anchor.y - h - 8;
  if (y < 8) y = anchor.y + anchor.h + 8;
  x = Math.max(8, Math.min(window.innerWidth - w - 8, x));

  return (
    <AnimatePresence>
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: 4, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 360, damping: 28 }}
        style={{ position: "fixed", left: x, top: y, width: w, maxHeight: h }}
        className="z-50 rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl flex flex-col overflow-hidden"
      >
        <div className="p-2 border-b border-border/60">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                // Enter picks the first *enabled* match — don't add a step
                // we'd immediately reject. Falls through silently if every
                // match is greyed (the user can scroll + click anyway).
                const target = filtered.find((s) => reqsByStep[s.id]?.ok ?? true);
                if (target) handlePick(target);
              }
            }}
            placeholder="Search steps…  (try 'filter', 'group')"
            className="w-full rounded-md bg-background border border-input px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
        <div className="overflow-y-auto flex-1 p-1">
          {/* AI ribbon: only shown when there's somewhere for the AI to
              draw context from (a real pipeline + a focused node). It
              hides itself when AI is disabled in Settings. Renders just
              under the search input — the most prominent slot. */}
          {/* Round-5 W1: previously hidden the moment the user typed
              anything. Keep it visible regardless of query so the
              "show me what AI suggests" affordance stays one click
              away. The ribbon's own internal logic decides whether
              to fetch a fresh suggestion. */}
          {pipelineId && focusedNodeId && (
            <AiRibbon
              pipelineId={pipelineId}
              focusedNodeId={focusedNodeId}
              focusedSchema={upstreamSchema ?? {}}
              steps={stepsQ.data ?? []}
              onApply={(s, params) => handlePick(s, params)}
            />
          )}
          {filtered.length === 0 && (
            <div className="text-xs text-muted-foreground p-3 text-center">
              No matches.
            </div>
          )}
          {/* Recently-used surfaces frequent picks at the top — without it,
              `filter_rows` is buried under "aggregate" alphabetically. Only
              shown when the user hasn't typed a search query. */}
          {!query.trim() && recent.length > 0 && stepsQ.data && (() => {
            const recentSteps = recent
              .map((id) => stepsQ.data!.find((s) => s.id === id))
              .filter((s): s is StepManifest => s !== undefined);
            if (recentSteps.length === 0) return null;
            return (
              <div className="mb-2">
                <p className="text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400 px-2 py-1">
                  🕘 recent
                </p>
                <ul>
                  {recentSteps.map((s) => (
                    <li key={`recent-${s.id}`}>
                      <StepRow step={s} req={reqsByStep[s.id]} onPick={handlePick} />
                    </li>
                  ))}
                </ul>
              </div>
            );
          })()}
          {/* Query mode: flat ranked list. The category visual hierarchy
              gets in the way when the user has expressed an intent. */}
          {grouped === null && (
            <ul>
              {filtered.map((s) => (
                <li key={s.id}>
                  <StepRow step={s} req={reqsByStep[s.id]} onPick={handlePick} />
                </li>
              ))}
            </ul>
          )}
          {grouped !== null && grouped.map(([cat, items]) => (
            <div key={cat} className="mb-2">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground/70 px-2 py-1">
                {CATEGORY_EMOJI[cat] ?? "🧩"} {cat}
              </p>
              <ul>
                {items.map((s) => (
                  <li key={s.id}>
                    <StepRow step={s} req={reqsByStep[s.id]} onPick={handlePick} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {/* Round-5 W1: "Don't see your step? Generate one" CTA — the
              ``/steps/new`` flow used to be reachable only from a never-
              mounted StepLibrary sidebar. */}
          <div className="border-t border-border/40 mt-2 pt-2 px-2 pb-1">
            <Link
              href="/steps/new"
              onClick={onClose}
              className="block text-[11px] text-muted-foreground hover:text-foreground transition-colors py-1.5"
              title="Open the AI-assisted custom-step authoring flow"
            >
              ✨ Don&apos;t see your step? Generate one →
            </Link>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─────────────────────────────────────────────────────────────────
// One row in the picker. Renders the step's label + description, and
// when the upstream schema doesn't satisfy the step's `requires`,
// dims the row + adds a tooltip explaining what's missing. We
// deliberately keep the row click-through enabled even when greyed —
// dropping a step on an incompatible upstream is allowed (the user
// might be planning to add a cast step before it), and the param
// form still surfaces validation errors at execute time. Greying
// communicates "this won't work as-is", not "you can't try."
// ─────────────────────────────────────────────────────────────────
function StepRow({
  step,
  req,
  onPick,
}: {
  step: StepManifest;
  req: ReturnType<typeof evaluateRequirements> | undefined;
  onPick: (s: StepManifest, paramsOverride?: Record<string, unknown>) => void;
}) {
  const ok = req?.ok ?? true;
  // Provenance: tint the row's background instead of taking
  // horizontal space with a chip. The source name shows up in the
  // hover tooltip — minimal at-a-glance noise, full info on demand.
  const packId = step.source && step.source.startsWith("pack:")
    ? step.source.slice(5)
    : null;
  // Pipeline-composite steps share a different tint (emerald) so
  // they're visually distinct from pack steps and built-ins.
  const pipelineSourceId = step.source && step.source.startsWith("pipeline:")
    ? step.source.slice(9)
    : null;
  const baseTooltip = !ok ? unmetTooltip(req!.unmet) : (step.description ?? "");
  const tooltip = pipelineSourceId
    ? `${step.label} · 🪆 composite from another pipeline${baseTooltip ? ` — ${baseTooltip}` : ""}`
    : packId
      ? `${step.label} · 📦 ${packId}${baseTooltip ? ` — ${baseTooltip}` : ""}`
      : baseTooltip;
  // Four states for the row background:
  //   1. greyed (requirements unmet) → opacity dim + faint hover
  //   2. pipeline-composite          → emerald tint
  //   3. pack-installed              → faint violet tint
  //   4. built-in                    → no tint, neutral hover
  let rowClass = "";
  if (!ok) {
    rowClass = "opacity-45 hover:opacity-70 hover:bg-muted/30";
  } else if (pipelineSourceId) {
    rowClass = "bg-emerald-50/60 hover:bg-emerald-100 dark:bg-emerald-950/30 dark:hover:bg-emerald-900/40";
  } else if (packId) {
    rowClass = "bg-violet-50/60 hover:bg-violet-100 dark:bg-violet-950/30 dark:hover:bg-violet-900/40";
  } else {
    rowClass = "hover:bg-muted/60";
  }
  return (
    <button
      type="button"
      onClick={() => onPick(step)}
      title={tooltip}
      className={`w-full text-left px-2 py-1.5 rounded text-sm transition-colors flex flex-col ${rowClass}`}
    >
      <span className="flex items-center gap-1.5">
        {!ok && (
          <span
            aria-hidden
            className="text-[10px] text-amber-600 dark:text-amber-400 select-none"
          >
            ⚠
          </span>
        )}
        <span className="flex-1 truncate">{step.label}</span>
      </span>
      {!ok ? (
        <span className="text-[10px] text-amber-700/80 dark:text-amber-300/80 truncate">
          {unmetTooltip(req!.unmet)}
        </span>
      ) : (
        step.description && (
          <span className="text-[10px] text-muted-foreground truncate">
            {step.description}
          </span>
        )
      )}
    </button>
  );
}

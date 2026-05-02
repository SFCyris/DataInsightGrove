"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type StepManifest } from "@/lib/api/client";

const CATEGORY_EMOJI: Record<string, string> = {
  ingest: "📥", shape: "✂️", clean: "🧹", derive: "➕",
  combine: "🔗", aggregate: "📊", model: "🧠", output: "📤", custom: "🧩",
};

interface Props {
  open: boolean;
  onClose: () => void;
  onPick: (step: StepManifest) => void;
  /** Anchor element rect (in viewport coords) — popover positions just above it. */
  anchor: { x: number; y: number; w: number; h: number } | null;
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

export function QuickAddMenu({ open, onClose, onPick, anchor }: Props) {
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const ref = useRef<HTMLDivElement>(null);

  const stepsQ = useQuery({ queryKey: ["steps"], queryFn: api.listSteps, staleTime: 60_000 });

  // Reload recent list each time the menu opens (cheap; no storage event listener).
  useEffect(() => {
    if (open) setRecent(readRecent());
  }, [open]);

  // Wrap onPick so we record usage. Defined here so anywhere that calls it
  // benefits — including the Enter-to-pick path below.
  const handlePick = (s: StepManifest) => {
    writeRecent(s.id);
    onPick(s);
  };

  useEffect(() => {
    if (open) {
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = stepsQ.data ?? [];
    if (!q) return list;
    return list.filter(
      (s) =>
        s.id.toLowerCase().includes(q) ||
        s.label.toLowerCase().includes(q) ||
        (s.description ?? "").toLowerCase().includes(q) ||
        (s.tags ?? []).some((t) => t.toLowerCase().includes(q)),
    );
  }, [query, stepsQ.data]);

  const grouped = useMemo(() => {
    const out: Record<string, StepManifest[]> = {};
    for (const s of filtered) (out[s.category] ||= []).push(s);
    return out;
  }, [filtered]);

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
              if (e.key === "Enter" && filtered.length > 0) {
                handlePick(filtered[0]);
              }
            }}
            placeholder="Search steps…  (try 'filter', 'group')"
            className="w-full rounded-md bg-background border border-input px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
        <div className="overflow-y-auto flex-1 p-1">
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
                      <button
                        type="button"
                        onClick={() => handlePick(s)}
                        className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-muted/60 transition-colors flex flex-col"
                      >
                        <span>{s.label}</span>
                        {s.description && (
                          <span className="text-[10px] text-muted-foreground truncate">
                            {s.description}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })()}
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat} className="mb-2">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground/70 px-2 py-1">
                {CATEGORY_EMOJI[cat] ?? "🧩"} {cat}
              </p>
              <ul>
                {items.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => handlePick(s)}
                      className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-muted/60 transition-colors flex flex-col"
                    >
                      <span>{s.label}</span>
                      {s.description && (
                        <span className="text-[10px] text-muted-foreground truncate">
                          {s.description}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

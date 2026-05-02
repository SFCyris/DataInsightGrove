"use client";

import { motion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type StepManifest } from "@/lib/api/client";

const CATEGORY_EMOJI: Record<string, string> = {
  ingest: "📥", shape: "✂️", clean: "🧹", derive: "➕",
  combine: "🔗", aggregate: "📊", output: "📤", custom: "🧩",
};

interface Props {
  onAdd: (step: StepManifest) => void;
}

export function StepLibrary({ onAdd }: Props) {
  const steps = useQuery({ queryKey: ["steps"], queryFn: api.listSteps, staleTime: 60_000 });

  const grouped: Record<string, StepManifest[]> = {};
  for (const s of steps.data ?? []) {
    (grouped[s.category] ||= []).push(s);
  }

  return (
    <aside className="w-[260px] shrink-0 border-r border-border bg-background/40 backdrop-blur p-3 overflow-y-auto">
      <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3 px-1">
        🧰 Step library
      </p>
      {steps.isLoading && (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-9 rounded-md bg-muted/40 animate-pulse" />
          ))}
        </div>
      )}
      {Object.entries(grouped).map(([cat, items], gi) => (
        <motion.div
          key={cat}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.04 * gi }}
          className="mb-4"
        >
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground/70 px-2 mb-1">
            {CATEGORY_EMOJI[cat] ?? "🧩"} {cat}
          </p>
          <ul className="space-y-1">
            {items.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onAdd(s)}
                  className="w-full text-left px-2 py-1.5 rounded-md text-sm hover:bg-muted/60 active:bg-muted transition-colors"
                  title={s.description}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        </motion.div>
      ))}
    </aside>
  );
}

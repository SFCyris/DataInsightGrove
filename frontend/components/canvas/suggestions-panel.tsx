"use client";

import { motion, AnimatePresence } from "motion/react";
import type { Suggestion } from "@/lib/suggestions";
import { HelpLink } from "@/components/help-link";

interface Props {
  suggestions: Suggestion[];
  onApply: (s: Suggestion) => void;
  onHover?: (column: string | null) => void;
  loading?: boolean;
}

const SEV_STYLE: Record<Suggestion["severity"], string> = {
  warn:
    "border-amber-300/50 bg-amber-50/40 dark:border-amber-700/40 dark:bg-amber-900/15",
  tip:
    "border-emerald-300/40 bg-emerald-50/30 dark:border-emerald-700/30 dark:bg-emerald-900/10",
  info:
    "border-border bg-card/50",
};

export function SuggestionsPanel({ suggestions, onApply, onHover, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 rounded-lg bg-muted/30 animate-pulse" />
        ))}
      </div>
    );
  }

  if (suggestions.length === 0) {
    return (
      <div className="text-center text-xs text-muted-foreground pt-12 px-4">
        <div className="text-3xl mb-2">✨</div>
        <p>
          No hints right now. The data looks clean — keep shaping, or try
          right-clicking a column header for direct actions.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
        <span>💡 Hints</span>
        <HelpLink topic="What hints are and how they work" anchor="4-the-editor--data-on-top-steps-on-bottom" />
        <span className="flex-1" />
        <span className="text-muted-foreground/60 normal-case tracking-normal">
          rule-based · not predictive
        </span>
      </div>

      <ul className="space-y-2">
        <AnimatePresence initial={false}>
          {suggestions.map((s) => (
            <motion.li
              key={s.id}
              layout
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ type: "spring", stiffness: 320, damping: 30 }}
              onMouseEnter={() => onHover?.(s.column)}
              onMouseLeave={() => onHover?.(null)}
              className={[
                "rounded-lg border px-3 py-2.5 text-xs",
                SEV_STYLE[s.severity],
              ].join(" ")}
            >
              <div className="flex items-start gap-2">
                <span aria-hidden className="text-base shrink-0">{s.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-foreground">{s.title}</p>
                  <p className="text-muted-foreground mt-0.5 leading-snug">{s.body}</p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 mt-2 justify-end">
                <button
                  type="button"
                  onClick={() => onApply(s)}
                  className="text-[11px] font-medium px-2 py-1 rounded-md bg-foreground text-background hover:opacity-90 transition-opacity"
                >
                  {s.applyLabel}
                </button>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>

      <p className="mt-4 text-[10px] text-muted-foreground/70 leading-snug">
        Hints are deterministic observations from the column profile — they
        suggest one specific step. Click <strong>Apply</strong> and the step is
        added to the pipeline; ⌘Z undoes.
      </p>
    </div>
  );
}

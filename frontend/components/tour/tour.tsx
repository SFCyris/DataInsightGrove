"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Button } from "@/components/ui/button";

export interface TourStep {
  /** Short title shown at the top of the tooltip. */
  title: string;
  /** Body — string or JSX. Keep it tight; this is a tour, not a docs page. */
  body: React.ReactNode;
  /** CSS selector for the element to spotlight. Omit for centered (welcome/end) steps. */
  target?: string;
  /** Where to place the tooltip relative to the target. Default 'auto'. */
  placement?: "top" | "bottom" | "left" | "right" | "auto";
  /** Optional callback fired when the user clicks "Next" on this step. */
  onNext?: () => void | Promise<void>;
  /** Override the next-button label, e.g. "Try it →". */
  nextLabel?: string;
}

interface Props {
  steps: TourStep[];
  open: boolean;
  onClose: () => void;
  storageKey?: string;
}

const PADDING = 12;

export function Tour({ steps, open, onClose, storageKey }: Props) {
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const step = steps[idx];

  // Reset to first step every time the tour opens.
  useEffect(() => {
    if (open) setIdx(0);
  }, [open]);

  // Track the spotlight rect (re-measure on resize/scroll).
  useLayoutEffect(() => {
    if (!open || !step?.target) {
      setRect(null);
      return;
    }
    const measure = () => {
      const el = document.querySelector(step.target!);
      if (el) setRect((el as HTMLElement).getBoundingClientRect());
      else setRect(null);
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    const t = setInterval(measure, 250); // simple way to follow async layouts
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      clearInterval(t);
    };
  }, [open, step?.target, idx]);

  if (!open || !step) return null;

  const isFirst = idx === 0;
  const isLast = idx === steps.length - 1;
  const handleNext = async () => {
    try {
      await step.onNext?.();
    } finally {
      if (isLast) {
        if (storageKey) {
          try {
            localStorage.setItem(storageKey, new Date().toISOString());
          } catch {
            /* ignore */
          }
        }
        onClose();
      } else {
        setIdx((i) => i + 1);
      }
    }
  };
  const handleSkip = () => {
    if (storageKey) {
      try {
        localStorage.setItem(storageKey, "skipped");
      } catch {
        /* ignore */
      }
    }
    onClose();
  };

  // Position the tooltip
  let tooltipStyle: React.CSSProperties = {
    position: "fixed",
    left: "50%",
    top: "50%",
    transform: "translate(-50%, -50%)",
    maxWidth: 360,
  };
  if (rect) {
    const placement = step.placement ?? "auto";
    const w = 360;
    const h = 220;
    let left = rect.left + rect.width / 2 - w / 2;
    let top = rect.bottom + PADDING + 8;
    if (placement === "top" || (placement === "auto" && top + h > window.innerHeight - 16)) {
      top = rect.top - PADDING - h - 8;
    }
    left = Math.max(16, Math.min(window.innerWidth - w - 16, left));
    top = Math.max(16, top);
    tooltipStyle = { position: "fixed", left, top, width: w, transform: "none" };
  }

  return (
    <AnimatePresence>
      <motion.div
        key="overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50"
      >
        {/* Backdrop with cut-out spotlight when targeting an element */}
        {rect ? (
          <svg
            className="absolute inset-0 w-full h-full pointer-events-auto"
            onClick={handleSkip}
          >
            <defs>
              <mask id="tour-spotlight">
                <rect x="0" y="0" width="100%" height="100%" fill="white" />
                <rect
                  x={Math.max(0, rect.left - PADDING)}
                  y={Math.max(0, rect.top - PADDING)}
                  width={rect.width + PADDING * 2}
                  height={rect.height + PADDING * 2}
                  rx={12}
                  ry={12}
                  fill="black"
                />
              </mask>
            </defs>
            <rect
              x="0" y="0" width="100%" height="100%"
              fill="rgba(0, 0, 0, 0.62)"
              mask="url(#tour-spotlight)"
            />
            <rect
              x={Math.max(0, rect.left - PADDING)}
              y={Math.max(0, rect.top - PADDING)}
              width={rect.width + PADDING * 2}
              height={rect.height + PADDING * 2}
              rx={12}
              ry={12}
              fill="none"
              stroke="rgba(180, 240, 200, 0.6)"
              strokeWidth={2}
              strokeDasharray="6 4"
              className="animate-pulse"
            />
          </svg>
        ) : (
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm pointer-events-auto"
            onClick={handleSkip}
          />
        )}

        {/* Tooltip / card */}
        <motion.div
          ref={tooltipRef}
          key={`step-${idx}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby={`tour-step-${idx}-title`}
          initial={{ opacity: 0, y: 8, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 4 }}
          transition={{ type: "spring", stiffness: 280, damping: 26 }}
          style={tooltipStyle}
          className="rounded-xl border border-border bg-card text-card-foreground shadow-2xl p-5 z-10"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
            <span aria-hidden>🧭</span>
            <span>Tour · {idx + 1}/{steps.length}</span>
          </div>
          <h3 id={`tour-step-${idx}-title`} className="text-base font-semibold mb-2">{step.title}</h3>
          <div className="text-sm text-muted-foreground leading-relaxed">
            {step.body}
          </div>
          <div className="flex items-center justify-between mt-5">
            <button
              type="button"
              onClick={handleSkip}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Skip tour
            </button>
            <div className="flex gap-2">
              {!isFirst && (
                <Button size="sm" variant="ghost" onClick={() => setIdx((i) => i - 1)}>
                  ← Back
                </Button>
              )}
              <Button size="sm" onClick={handleNext}>
                {step.nextLabel ?? (isLast ? "Done ✓" : "Next →")}
              </Button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

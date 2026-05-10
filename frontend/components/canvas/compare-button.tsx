"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { Button } from "@/components/ui/button";
import { PipelineDiffView } from "@/components/pipeline-diff-view";

/**
 * "↔ Compare" button on the pipeline editor toolbar.
 *
 * Opens a side drawer (right-anchored, ~620px) containing the
 * <PipelineDiffView />. Drawer respects reduced-motion and closes on Esc.
 */
export function CompareButton({ pipelineId }: { pipelineId: string }) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => setOpen(true)}
        title="Compare this pipeline to a previous version (snapshots auto-save on every change)"
        aria-label="Compare pipeline versions"
      >
        ↔ Compare
      </Button>

      {/* Portal to <body> so the fixed drawer escapes the editor header's
          stacking context (the header is `position: relative`). */}
      {typeof document !== "undefined" && createPortal(
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm"
              onClick={() => setOpen(false)}
            />
            <motion.aside
              initial={reduce ? { opacity: 0 } : { x: "100%" }}
              animate={reduce ? { opacity: 1 } : { x: 0 }}
              exit={reduce ? { opacity: 0 } : { x: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="fixed right-0 top-0 bottom-0 z-50 w-[min(720px,100vw)] bg-background border-l border-border shadow-2xl flex flex-col"
              role="dialog"
              aria-label="Pipeline diff"
            >
              <div className="flex items-center justify-end px-3 py-2 border-b border-border">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="text-xs text-muted-foreground hover:text-foreground rounded px-2 py-1 hover:bg-muted"
                  aria-label="Close diff drawer"
                >
                  Close ✕
                </button>
              </div>
              <div className="flex-1 min-h-0">
                <PipelineDiffView pipelineId={pipelineId} />
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>,
      document.body)}
    </>
  );
}

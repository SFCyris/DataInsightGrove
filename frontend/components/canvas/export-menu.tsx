"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { toast } from "sonner";

/**
 * Single-button export menu — replaces the prior trio of icon buttons
 * (📤 / 🐍 / 📓) which were visual clutter for a low-frequency action.
 */
export function ExportMenu({ pipelineId }: { pipelineId: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on click outside or escape (keyboard nav).
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const download = (filename: string, content: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    // Defer revoke to next tick — Safari + older Firefox can race the
    // download dispatch with a synchronous revoke and produce a 0-byte
    // file. Holding the URL for one tick is plenty.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const exportDig = async () => {
    setOpen(false);
    try {
      const env = await api.exportPipeline(pipelineId);
      const safe = (env.name || "pipeline").replace(/[^a-z0-9._-]+/gi, "_").toLowerCase();
      download(`${safe}.dig.json`, JSON.stringify(env, null, 2), "application/json");
      toast.success("📤 Pipeline exported");
    } catch (e) {
      toast.error(`Export failed: ${(e as Error).message}`);
    }
  };
  const exportPy = async () => {
    setOpen(false);
    try {
      const r = await api.exportPipelinePython(pipelineId);
      const safe = (r.name || "pipeline").replace(/[^a-z0-9._-]+/gi, "_").toLowerCase();
      download(`${safe}.py`, r.code, "text/x-python");
      // Surface unsupported steps loudly so users don't end up with a
      // silently-broken .py — the script still downloads (it has TODO
      // markers inline), but the toast tells them what they need to fix.
      if (r.unsupportedSteps && r.unsupportedSteps.length > 0) {
        toast.warning(
          `🐍 Python downloaded — ${r.unsupportedSteps.length} step(s) need manual fill-in: ${r.unsupportedSteps.join(", ")}`,
          { duration: 8000 },
        );
      } else {
        toast.success("🐍 Python script downloaded");
      }
    } catch (e) {
      toast.error(`Python export failed: ${(e as Error).message}`);
    }
  };
  const exportIpynb = async () => {
    setOpen(false);
    try {
      const nb = await api.exportPipelineNotebook(pipelineId);
      const name = (nb["dig_pipeline_name"] as string) || "pipeline";
      const safe = name.replace(/[^a-z0-9._-]+/gi, "_").toLowerCase();
      download(`${safe}.ipynb`, JSON.stringify(nb, null, 2), "application/x-ipynb+json");
      toast.success("📓 Notebook downloaded");
    } catch (e) {
      toast.error(`Notebook export failed: ${(e as Error).message}`);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <Button
        size="sm"
        variant="ghost"
        title="Export this pipeline"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        📤 Export ▾
      </Button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 360, damping: 28 }}
            className="absolute right-0 top-full mt-1 z-30 min-w-[220px] rounded-lg border border-border bg-popover shadow-lg p-1"
          >
            <MenuItem emoji="📤" label="Pipeline (.dig.json)" sub="Reusable, importable" onClick={exportDig} />
            <MenuItem emoji="🐍" label="Polars script (.py)" sub="Run anywhere with Python" onClick={exportPy} />
            <MenuItem emoji="📓" label="Jupyter notebook (.ipynb)" sub="Cell-by-cell walkthrough" onClick={exportIpynb} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MenuItem({
  emoji, label, sub, onClick,
}: { emoji: string; label: string; sub: string; onClick: () => void }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="w-full flex items-start gap-2 px-2.5 py-2 rounded-md hover:bg-muted text-left"
    >
      <span className="text-lg leading-none mt-0.5" aria-hidden>{emoji}</span>
      {/* Inline spans with `block` — <button> only allows phrasing content. */}
      <span className="inline-flex flex-col">
        <span className="block text-sm font-medium">{label}</span>
        <span className="block text-[11px] text-muted-foreground">{sub}</span>
      </span>
    </button>
  );
}

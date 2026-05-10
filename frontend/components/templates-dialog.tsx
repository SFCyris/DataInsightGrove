"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api/client";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function TemplatesDialog({ open, onClose }: Props) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const list = useQuery({
    queryKey: ["templates"],
    queryFn: api.listTemplates,
    enabled: open,
    staleTime: 60_000,
  });

  const create = useMutation({
    mutationFn: (slug: string) => api.createFromTemplate(slug),
    onSuccess: (p) => {
      toast.success(`✨ Pipeline created from template`);
      queryClient.invalidateQueries({ queryKey: ["pipelines"] });
      onClose();
      router.push(`/pipelines/${p.id}`);
    },
    onError: (e: Error) => toast.error(`Template apply failed: ${e.message}`),
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50"
        >
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(720px,92vw)] max-h-[80vh] overflow-hidden rounded-xl border border-border bg-card shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="px-5 py-3 border-b border-border flex items-center gap-3">
              <span className="text-2xl">📦</span>
              <div className="flex-1">
                <p className="text-[11px] uppercase tracking-widest text-muted-foreground">
                  Start from a template
                </p>
                <h2 className="text-lg font-semibold tracking-tight">
                  Pre-built pipelines you can poke at
                </h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Close"
              >
                ✕
              </button>
            </header>

            <div className="flex-1 overflow-auto p-5 space-y-3">
              {list.isLoading && (
                <div className="space-y-2">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="h-24 rounded-lg bg-muted/40 animate-pulse" />
                  ))}
                </div>
              )}
              {list.data?.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-12">
                  No templates bundled. Drop one under{" "}
                  <code>samples/templates/</code> in the repo.
                </p>
              )}
              {list.data?.map((t) => (
                <motion.button
                  key={t.slug}
                  whileHover={{ y: -1 }}
                  whileTap={{ scale: 0.99 }}
                  type="button"
                  disabled={create.isPending}
                  onClick={() => create.mutate(t.slug)}
                  className="w-full text-left rounded-xl border border-border bg-card hover:border-foreground/30 transition-colors p-4 flex items-start gap-4"
                >
                  <span className="text-3xl shrink-0" aria-hidden>
                    {t.title.split(" ")[0]}
                  </span>
                  {/* Phrasing-only children inside <button> — was <h3>+<p>+<div>
                      which React 19 hydration warns on. Inline-flex spans
                      with `block` give the same visual stack. */}
                  <span className="flex-1 min-w-0 inline-flex flex-col items-start">
                    <span className="block font-medium">
                      {t.title.split(" ").slice(1).join(" ")}
                    </span>
                    <span className="block text-xs text-muted-foreground mt-1 leading-relaxed">
                      {t.summary}
                    </span>
                    <span className="inline-flex items-center gap-2 mt-2 flex-wrap">
                      <span className="text-[10px] tabular-nums text-muted-foreground/80">
                        {t.stepCount} step{t.stepCount === 1 ? "" : "s"}
                      </span>
                      {t.needsSampleDataset && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-emerald-300/40 text-emerald-700 dark:text-emerald-300">
                          uses 🌱 demo data
                        </span>
                      )}
                      {t.tags.slice(0, 3).map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted/60 text-muted-foreground"
                        >
                          {tag}
                        </span>
                      ))}
                    </span>
                  </span>
                  <span className="text-muted-foreground/60 shrink-0 self-center">
                    {create.isPending ? "⏳" : "→"}
                  </span>
                </motion.button>
              ))}
            </div>

            <footer className="px-5 py-2 border-t border-border text-[11px] text-muted-foreground">
              Templates create a new pipeline (and import the demo dataset if needed). Nothing is overwritten.
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

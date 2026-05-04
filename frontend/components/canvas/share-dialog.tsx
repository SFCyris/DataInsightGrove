"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { useExpertise } from "@/lib/settings";
import { Button } from "@/components/ui/button";

interface Props {
  pipelineId: string;
  pipelineName: string;
}

/**
 * "🔗 Share" button + dialog. Gated to Builder+.
 *
 * Public visibility is force-coerced to "unlisted" by the backend until a
 * curation review pass is added — see PUBLIC_TEMPLATE_GALLERY.md.
 */
export function ShareDialog({ pipelineId, pipelineName }: Props) {
  const { isAtLeast } = useExpertise();
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(pipelineName);
  const [summary, setSummary] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");
  const [authorHandle, setAuthorHandle] = useState("");
  const [visibility, setVisibility] = useState<"private" | "unlisted" | "public">("unlisted");

  useEffect(() => {
    if (open) setTitle(pipelineName);
  }, [open, pipelineName]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const create = useMutation({
    mutationFn: () =>
      api.createGalleryTemplate({
        pipelineId,
        title: title.trim() || pipelineName,
        summary: summary.trim() || undefined,
        tags: tagsRaw
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        authorHandle: authorHandle.trim() || undefined,
        visibility,
      }),
    onSuccess: (t) => {
      const url = `${window.location.origin}/gallery/${t.slug}`;
      navigator.clipboard?.writeText(url).catch(() => {});
      // Surface the public→unlisted coercion explicitly. Hiding it in a
      // fine-print disclaimer below the radio led users to believe they had
      // published publicly when they hadn't.
      const msg =
        visibility === "public"
          ? "✅ Published as Unlisted (Public requires curation review) — link copied"
          : "✅ Template published — link copied to clipboard";
      toast.success(msg);
      setOpen(false);
    },
    onError: (e: Error) => toast.error(`Share failed: ${e.message}`),
  });

  if (!isAtLeast("builder")) return null;

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => setOpen(true)}
        title="Share this pipeline as a template"
      >
        🔗 Share
      </Button>

      {/* Portal so the modal escapes the toolbar header's stacking context. */}
      {typeof document !== "undefined" && createPortal(
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
              onClick={() => setOpen(false)}
            />
            <motion.div
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.97 }}
              animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.97 }}
              transition={{ type: "spring", stiffness: 320, damping: 28 }}
              className="fixed left-1/2 top-[15vh] -translate-x-1/2 z-50 w-[min(560px,92vw)] rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl p-6"
              role="dialog"
              aria-label="Share pipeline as template"
            >
              <header className="mb-4">
                <h2 className="text-lg font-semibold tracking-tight">🔗 Share this pipeline</h2>
                <p className="text-xs text-muted-foreground mt-1">
                  Saves a snapshot to your local DIG's template gallery. Connection IDs and inline secrets are stripped.
                </p>
              </header>

              <div className="space-y-3">
                <Field label="Title">
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </Field>
                <Field label="Summary" hint="One paragraph; markdown supported in the detail page.">
                  <textarea
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                    rows={3}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </Field>
                <Field label="Tags" hint="Comma-separated, e.g. cleanup, customers, beginner.">
                  <input
                    type="text"
                    value={tagsRaw}
                    onChange={(e) => setTagsRaw(e.target.value)}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </Field>
                <Field label="Author handle" hint="Optional. Shown on the template detail page.">
                  <input
                    type="text"
                    value={authorHandle}
                    onChange={(e) => setAuthorHandle(e.target.value)}
                    placeholder="yourname"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </Field>
                <Field label="Visibility">
                  <div className="flex gap-2">
                    {(["private", "unlisted", "public"] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => setVisibility(v)}
                        className={[
                          "flex-1 rounded-md border px-3 py-2 text-xs transition-colors",
                          visibility === v
                            ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20"
                            : "border-border hover:border-foreground/30",
                        ].join(" ")}
                      >
                        {v === "private" && "🔒 Private"}
                        {v === "unlisted" && "🔗 Unlisted"}
                        {v === "public" && "🌍 Public"}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1.5 text-[10px] text-muted-foreground">
                    "Public" submissions are surfaced as Unlisted until a curation review.
                  </p>
                </Field>
              </div>

              <footer className="mt-6 flex items-center justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={() => create.mutate()}
                  disabled={create.isPending || !title.trim()}
                >
                  {create.isPending ? "⏳ Sharing…" : "🔗 Share"}
                </Button>
              </footer>
            </motion.div>
          </>
        )}
      </AnimatePresence>,
      document.body)}
    </>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs text-muted-foreground block mb-1">{label}</span>
      {children}
      {hint && <span className="text-[10px] text-muted-foreground/80 block mt-1">{hint}</span>}
    </label>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type PipelineSummary } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { confirmAction } from "@/lib/confirm-toast";
import { toastError } from "@/lib/toast-error";

/**
 * PipelineCard — single tile in the pipelines library grid.
 *
 * Mirrors DatasetCard so the two list pages feel identical:
 *   - Click anywhere in the card to open it
 *   - "🗑 Remove" reveals on hover or focus-within (a11y), runs a
 *     confirm() dialog and a toast-on-result mutation
 *   - When the backend reports `missingDatasetCount` or `missingOutputCount`
 *     a "⚠ Missing data" badge replaces the green "ready" pill, with a
 *     tooltip listing exactly what's gone. This catches the common case of
 *     "I deleted the demo dataset and now my sample template is broken".
 */
export function PipelineCard({
  p,
  index,
  running = false,
}: {
  p: PipelineSummary;
  index: number;
  /** Round-6 UX#4: whether the parent has detected a queued/running
   *  run for this pipeline. Drives the 🔄 running pill. */
  running?: boolean;
}) {
  const queryClient = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.deletePipeline(p.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pipelines"] });
      toast.success(`🗑 Removed "${p.name}"`);
    },
    onError: (e: Error) => toastError("Delete failed", e),
  });

  // Round-5 W5: favorite/star toggle. Pinned pipelines sort to the top
  // of the list page and surface with a ⭐ prefix in cmdk.
  const [fav, setFav] = useState(false);
  // Tracks the in-flight download so the button can show a spinner
  // and a duplicate click is suppressed.
  const [downloading, setDownloading] = useState(false);
  useEffect(() => {
    import("@/lib/recent-items").then(({ isFavorite }) => {
      setFav(isFavorite("pipeline", p.id));
    });
  }, [p.id]);
  const onToggleFav = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    import("@/lib/recent-items").then(({ toggleFavorite }) => {
      const next = toggleFavorite("pipeline", p.id);
      setFav(next);
      toast(next ? `⭐ Pinned "${p.name}"` : `Unpinned`);
    });
  };

  const missingInputs = p.missingDatasetCount ?? 0;
  const missingOutputs = p.missingOutputCount ?? 0;
  const hasMissing = missingInputs > 0 || missingOutputs > 0;
  // Detect a leading emoji in the user-chosen name. If present, we
  // suppress the decorative 🛤 prefix to avoid the "two adjacent
  // emojis" rendering the QA agent flagged. Lifted out of the JSX
  // (was an IIFE inline) because SWC's parser was tripping on the
  // (() => {...})() construct sitting between two JSX siblings.
  const startsWithEmoji = /^\p{Extended_Pictographic}/u.test(p.name);

  // Build a precise tooltip so the user knows what to fix without having
  // to open the editor. Both counts are always shown when nonzero so the
  // copy reads naturally in either case ("2 inputs", "1 output", or both).
  const missingTitle = hasMissing
    ? [
        missingInputs > 0
          ? `${missingInputs} input dataset${missingInputs === 1 ? "" : "s"} missing`
          : null,
        missingOutputs > 0
          ? `${missingOutputs} output file${missingOutputs === 1 ? "" : "s"} missing`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : undefined;

  return (
    <motion.li
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 320,
        damping: 30,
        delay: 0.04 * index,
      }}
      className="group rounded-xl border border-border bg-card hover:border-foreground/30 transition-colors"
    >
      <Link
        href={`/pipelines/${p.id}`}
        className="flex flex-col gap-2 p-4 outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {/* Round-5 W5: pin/favorite toggle. Clicking the star
                doesn't navigate (preventDefault) so the user can pin
                without opening the pipeline. */}
            <button
              type="button"
              onClick={onToggleFav}
              title={fav ? "Unpin from favorites" : "Pin to favorites"}
              aria-label={fav ? "Unpin pipeline" : "Pin pipeline"}
              aria-pressed={fav}
              className={cn(
                "text-base shrink-0 transition-opacity",
                fav
                  ? "text-amber-400 opacity-100"
                  : "text-muted-foreground opacity-30 hover:opacity-90",
              )}
            >
              {fav ? "⭐" : "☆"}
            </button>
            {!startsWithEmoji && (
              <span className="text-xl select-none" aria-hidden>🛤</span>
            )}
            <div className="min-w-0">
              <p className="font-medium truncate">{p.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                pipeline · {p.id.slice(-8)}
              </p>
            </div>
          </div>
          {running ? (
            <span
              title="A run is queued or in progress for this pipeline"
              className={cn(
                "text-xs px-2 py-0.5 rounded-full border whitespace-nowrap inline-flex items-center gap-1",
                "border-sky-300 bg-sky-50 text-sky-800",
                "dark:border-sky-700 dark:bg-sky-950 dark:text-sky-200",
              )}
            >
              <span className="relative inline-flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75 animate-ping" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-sky-500" />
              </span>
              🔄 running
            </span>
          ) : hasMissing ? (
            <span
              title={missingTitle}
              className={cn(
                "text-xs px-2 py-0.5 rounded-full border whitespace-nowrap",
                "border-amber-300 bg-amber-50 text-amber-800",
                "dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200",
              )}
            >
              ⚠ Missing data
            </span>
          ) : (
            <span
              className={cn(
                "text-xs px-2 py-0.5 rounded-full border whitespace-nowrap",
                "border-green-200 bg-green-50 text-green-700",
                "dark:border-green-900 dark:bg-green-950 dark:text-green-300",
              )}
            >
              ✅ ready
            </span>
          )}
        </div>
        <dl className="grid grid-cols-3 gap-3 text-xs text-muted-foreground tabular-nums pt-1">
          <div>
            <dt className="uppercase tracking-wider opacity-60">Datasets</dt>
            <dd
              className={cn(
                "font-medium",
                missingInputs > 0 ? "text-amber-600 dark:text-amber-300" : "text-foreground",
              )}
            >
              {missingInputs > 0
                ? `${p.datasetCount} (${missingInputs} ⚠)`
                : p.datasetCount}
            </dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider opacity-60">Steps</dt>
            <dd className="font-medium text-foreground">{p.nodeCount}</dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider opacity-60">Outputs</dt>
            <dd
              className={cn(
                "font-medium",
                missingOutputs > 0 ? "text-amber-600 dark:text-amber-300" : "text-foreground",
              )}
            >
              {missingOutputs > 0
                ? `${p.outputCount} (${missingOutputs} ⚠)`
                : p.outputCount}
            </dd>
          </div>
        </dl>
      </Link>
      {/* focus-within keeps the download / delete buttons reachable for
          keyboard users who can't reveal them with a hover. (a11y
          review finding) */}
      <div className="flex items-center justify-between px-3 pb-3 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
        <Button
          size="xs"
          variant="ghost"
          disabled={downloading}
          title={`Download "${p.name}" as a .dig.json envelope`}
          onClick={async (e) => {
            e.preventDefault();
            setDownloading(true);
            try {
              const envelope = await api.exportPipeline(p.id);
              const blob = new Blob(
                [JSON.stringify(envelope, null, 2)],
                { type: "application/json" },
              );
              // File-safe slug: lowercase, replace non-alphanum/. with -.
              const slug = (p.name || p.id)
                .toLowerCase()
                .replace(/[^a-z0-9.]+/g, "-")
                .replace(/^-+|-+$/g, "");
              const filename = `${slug || "pipeline"}.dig.json`;
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = filename;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
              toast.success(`Downloaded ${filename}`);
            } catch (err) {
              toastError("Download failed", err);
            } finally {
              setDownloading(false);
            }
          }}
        >
          {downloading ? "⏳ Downloading…" : "⬇ Download"}
        </Button>
        <Button
          size="xs"
          variant="ghost"
          disabled={del.isPending}
          aria-label={del.isPending ? "Removing pipeline" : "Remove pipeline"}
          onClick={async (e) => {
            e.preventDefault();
            const ok = await confirmAction({
              title: `Remove "${p.name}"?`,
              description:
                "This deletes the pipeline definition and run history. " +
                "Datasets are not affected.",
              confirmLabel: "Remove",
            });
            if (ok) del.mutate();
          }}
        >
          {del.isPending ? "⏳" : "🗑"} Remove
        </Button>
      </div>
    </motion.li>
  );
}

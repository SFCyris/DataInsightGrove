"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Dataset } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fmtInt } from "@/lib/format-number";
import { confirmAction } from "@/lib/confirm-toast";
import { toastError } from "@/lib/toast-error";

const STATUS_EMOJI: Record<string, string> = {
  ready: "✅",
  ingesting: "⏳",
  failed: "❌",
  registering: "🟡",
  awaiting_sheet_pick: "📑",
  awaiting_island_pick: "📐",
};

const STATUS_LABEL: Record<string, string> = {
  awaiting_sheet_pick: "pick a sheet",
  awaiting_island_pick: "pick a table",
};

function fmtBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function DatasetCard({ d, index }: { d: Dataset; index: number }) {
  const queryClient = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.deleteDataset(d.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      toast.success(`🗑 Removed "${d.name}"`);
    },
    onError: (e: Error) => toastError("Delete failed", e),
  });

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
        href={`/datasets/${d.id}`}
        className="flex flex-col gap-2 p-4 outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xl select-none" aria-hidden>
              📊
            </span>
            <div className="min-w-0">
              <p className="font-medium truncate">{d.name}</p>
              <p className="text-xs text-muted-foreground truncate">{d.connector} · {d.id.slice(-8)}</p>
            </div>
          </div>
          <span
            className={cn(
              "text-xs px-2 py-0.5 rounded-full border",
              d.status === "ready"
                ? "border-green-200 bg-green-50 text-green-700 dark:border-green-900 dark:bg-green-950 dark:text-green-300"
                : d.status === "failed"
                  ? "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
                  : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
            )}
          >
            {STATUS_EMOJI[d.status] ?? "❔"} {STATUS_LABEL[d.status] ?? d.status}
          </span>
        </div>
        <dl className="grid grid-cols-3 gap-3 text-xs text-muted-foreground tabular-nums pt-1">
          <div>
            <dt className="uppercase tracking-wider opacity-60">Rows</dt>
            <dd className="font-medium text-foreground">
              {fmtInt(d.rowCount)}
            </dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider opacity-60">Cols</dt>
            <dd className="font-medium text-foreground">
              {d.columns?.length ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="uppercase tracking-wider opacity-60">Size</dt>
            <dd className="font-medium text-foreground">{fmtBytes(d.fileSize)}</dd>
          </div>
        </dl>
      </Link>
      {/* focus-within keeps the delete button reachable for keyboard users
          who can't reveal it with a hover. (a11y review finding) */}
      <div className="flex justify-end px-3 pb-3 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
        <Button
          size="xs"
          variant="ghost"
          disabled={del.isPending}
          aria-label={del.isPending ? "Removing dataset" : "Remove dataset"}
          onClick={async (e) => {
            e.preventDefault();
            const ok = await confirmAction({
              title: `Remove "${d.name}"?`,
              description:
                "This deletes the cached data + source file. " +
                "Any pipeline that references this dataset by ID will need to be re-pointed.",
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

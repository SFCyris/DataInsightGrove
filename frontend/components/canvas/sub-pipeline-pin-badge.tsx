"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

/**
 * Badge shown in the params panel when a node is a sub-pipeline step.
 * Displays the pinned etag and offers a one-click "Upgrade to vN"
 * button when the source pipeline has advanced past the pinned
 * version.
 *
 * Pinning is intentional — when a parent installs a sub-pipeline,
 * the parent's compiled output stays stable until the user
 * explicitly upgrades. This avoids surprise behaviour changes when
 * the sub-pipeline author iterates on their copy — the
 * surprise-breakage failure mode of tools that auto-update shared
 * macro definitions underneath dependent calcs.
 */
interface Props {
  step: string;        // "pipeline:<id>"
  pinnedEtag: number;
  onUpgrade: (toEtag: number) => void;
}

export function SubPipelinePinBadge({ step, pinnedEtag, onUpgrade }: Props) {
  const sourceId = step.startsWith("pipeline:") ? step.slice(9) : step;

  // Fetch the source pipeline to discover its current etag. Cached for
  // a minute — the source isn't changing every keystroke.
  const q = useQuery({
    queryKey: ["pipeline-source-etag", sourceId],
    queryFn: () => api.getPipeline(sourceId),
    staleTime: 60_000,
    retry: false,
  });

  const liveEtag = q.data?.etag ?? null;
  const behind = liveEtag != null && liveEtag > pinnedEtag ? liveEtag - pinnedEtag : 0;

  return (
    <div className="rounded-md border border-emerald-200/60 bg-emerald-50/50 dark:bg-emerald-900/15 dark:border-emerald-700/40 px-2.5 py-1.5 mb-3 text-[11px] flex items-center gap-2">
      <span aria-hidden>🪆</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-emerald-900 dark:text-emerald-200">
          Sub-pipeline · pinned to v{pinnedEtag}
        </p>
        {q.isLoading && (
          <p className="text-muted-foreground">Checking source for updates…</p>
        )}
        {q.isError && (
          <p className="text-rose-600 dark:text-rose-400">
            Source pipeline unavailable — it may have been deleted.
          </p>
        )}
        {liveEtag != null && behind === 0 && (
          <p className="text-muted-foreground">Up to date with source.</p>
        )}
        {liveEtag != null && behind > 0 && (
          <p className="text-amber-700 dark:text-amber-300">
            {behind} version{behind === 1 ? "" : "s"} behind source (v{liveEtag}).
          </p>
        )}
      </div>
      {liveEtag != null && behind > 0 && (
        <Button
          size="xs"
          variant="default"
          onClick={() => onUpgrade(liveEtag)}
          title={`Upgrade pin from v${pinnedEtag} to v${liveEtag}`}
        >
          ⬆ Upgrade to v{liveEtag}
        </Button>
      )}
    </div>
  );
}

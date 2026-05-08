"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Dataset } from "@/lib/api/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { DatasetGrid } from "@/components/grid/dataset-grid";
import { ProfileCard } from "@/components/profile/profile-card";
import { SheetPickerModal } from "@/components/sheet-picker-modal";
import { IslandPickerModal } from "@/components/island-picker-modal";
import { fmtInt } from "@/lib/format-number";

function _datasetRefId(id: string): string {
  return `ds_${id.toLowerCase()}`;
}

type PageProps = { params: Promise<{ id: string }> };

export default function DatasetDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const reduce = useReducedMotion();
  const router = useRouter();
  const [shaping, setShaping] = useState(false);

  const dataset = useQuery({
    queryKey: ["dataset", id],
    queryFn: () => api.getDataset(id),
    refetchInterval: (q) => (q.state.data?.status === "ingesting" ? 1500 : false),
  });

  // Workflow CTA: create a fresh pipeline pre-attached to this dataset and
  // navigate straight into the editor. Closes the largest UX gap from the
  // review (a user with a freshly imported dataset previously had to back
  // out → click 🛤 Pipelines → name a pipeline → re-add the dataset).
  const shapeInPipeline = useMutation({
    mutationFn: async () => {
      if (!dataset.data) throw new Error("dataset not loaded");
      const refId = _datasetRefId(dataset.data.id);
      const uri = dataset.data.storageUri ?? dataset.data.sourceUri;
      const connector = dataset.data.storageUri ? "parquet" : dataset.data.connector;
      const doc = {
        schemaVersion: 1 as const,
        id: "PLACEHOLDER",
        name: `${dataset.data.name} — pipeline`,
        datasets: [{
          id: refId, connector, uri,
          label: dataset.data.name,
        }],
        nodes: [], outputs: [],
      };
      return api.createPipeline(doc.name, doc);
    },
    onSuccess: (res) => {
      // Optimistic toast: the success state is rendered before the route
      // change is observable, so the action feels instantaneous.
      toast.success(`✨ Created "${res.document.name}" — opening editor…`);
      router.push(`/pipelines/${res.id}`);
    },
    onError: (e: Error) => {
      setShaping(false);
      toast.error(`Couldn't create pipeline: ${e.message}`);
    },
  });

  // "🚀 Get a head start" — quick path to a chart-ful pipeline. Calls the
  // backend's column-profile heuristic (most variable numeric → histogram,
  // lowest-cardinality categorical → bar) and lands the user on a pipeline
  // already rendering 1–3 charts via the live image preview path. The big
  // blank-canvas vs. multi-step setup gap is the dominant friction for
  // first-time DIG users; this collapses it to one click.
  const generateOverview = useMutation({
    mutationFn: async () => {
      if (!dataset.data) throw new Error("dataset not loaded");
      return api.createPipelineFromDataset(dataset.data.id);
    },
    onSuccess: (res) => {
      toast.success(
        `🚀 Generated overview pipeline — ${(res.document.nodes as { id: string }[] | undefined)?.length ?? 0} chart(s)`,
      );
      router.push(`/pipelines/${res.id}`);
    },
    onError: (e: Error) => toast.error(`Overview failed: ${e.message}`),
  });
  const profile = useQuery({
    queryKey: ["dataset", id, "profile"],
    queryFn: () => api.getProfile(id),
    enabled: dataset.data?.status === "ready",
  });

  const fadeUp = reduce
    ? { initial: false, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 },
      };

  return (
    <main id="main" className="flex flex-1 flex-col p-8 gap-6 max-w-[1400px] w-full mx-auto">
      <motion.header {...fadeUp} className="flex items-center justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/datasets"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
            aria-label="Back to datasets"
          >
            ← Datasets
          </Link>
          <span className="text-2xl select-none" aria-hidden>
            📊
          </span>
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-widest text-muted-foreground">
              Dataset
            </p>
            <h1 className="text-2xl font-semibold tracking-tight truncate">
              {dataset.data?.name ?? "…"}
            </h1>
          </div>
        </div>
        {dataset.data && (
          <div className="flex items-center gap-6">
            <dl className="flex items-center gap-6 text-sm tabular-nums">
              <div className="text-right">
                <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Rows
                </dt>
                <dd className="font-medium">{fmtInt(dataset.data.rowCount)}</dd>
              </div>
              <div className="text-right">
                <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Columns
                </dt>
                <dd className="font-medium">{dataset.data.columns?.length ?? "—"}</dd>
              </div>
              <div className="text-right">
                <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Status
                </dt>
                <dd className="font-medium">
                  {dataset.data.status === "ready" && "✅ ready"}
                  {dataset.data.status === "ingesting" && "⏳ ingesting"}
                  {dataset.data.status === "failed" && "❌ failed"}
                </dd>
              </div>
            </dl>
            <div className="flex flex-col items-stretch gap-2">
              <Button
                size="lg"
                disabled={dataset.data.status !== "ready" || generateOverview.isPending || shaping || shapeInPipeline.isPending}
                onClick={() => generateOverview.mutate()}
                className="!bg-emerald-500 !text-emerald-950 hover:!bg-emerald-400"
                title="Auto-build a 1–3-chart overview pipeline from this dataset's column profile and open it. Charts render live in seconds."
              >
                {generateOverview.isPending ? "🚀 Generating…" : "🚀 Generate overview →"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={dataset.data.status !== "ready" || shaping || shapeInPipeline.isPending || generateOverview.isPending}
                onClick={() => { setShaping(true); shapeInPipeline.mutate(); }}
                className="text-xs"
                title="Create an empty pipeline pre-attached to this dataset — start from scratch"
              >
                {shaping || shapeInPipeline.isPending ? "✨ Opening…" : "✂️ Or start from scratch"}
              </Button>
            </div>
          </div>
        )}
      </motion.header>

      {dataset.error && (
        <p className="text-sm text-destructive">
          ❌ {(dataset.error as Error).message}
        </p>
      )}

      {dataset.data?.status === "failed" && (
        <p className="text-sm text-destructive border border-destructive/20 bg-destructive/10 rounded-lg p-3">
          ❌ {dataset.data.error ?? "Ingest failed."}
        </p>
      )}

      {dataset.data?.status === "ingesting" && (
        <div className="text-sm text-muted-foreground border border-border bg-muted/20 rounded-lg p-6 text-center">
          ⏳ Ingesting…
        </div>
      )}

      {dataset.data?.status === "awaiting_sheet_pick" && (
        <AwaitingSheetPick dataset={dataset.data} onPicked={() => dataset.refetch()} />
      )}

      {dataset.data?.status === "awaiting_island_pick" && (
        <AwaitingIslandPick dataset={dataset.data} onPicked={() => dataset.refetch()} />
      )}

      {profile.data && profile.data.columns.length > 0 && (
        <motion.section
          {...fadeUp}
          transition={{ ...("transition" in fadeUp ? fadeUp.transition : {}), delay: 0.05 }}
          className="flex flex-col gap-2"
        >
          <h2 className="text-xs uppercase tracking-widest text-muted-foreground">
            <span className="mr-1">📈</span> Profile
          </h2>
          <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
            {profile.data.columns.map((c, i) => (
              <ProfileCard key={c.name} column={c} index={i} />
            ))}
          </div>
        </motion.section>
      )}

      {dataset.data?.status === "ready" && profile.data && (
        <motion.section
          {...fadeUp}
          transition={{ ...("transition" in fadeUp ? fadeUp.transition : {}), delay: 0.1 }}
          className="flex flex-col gap-2"
        >
          <h2 className="text-xs uppercase tracking-widest text-muted-foreground">
            <span className="mr-1">🔢</span> Rows
          </h2>
          <div className="rounded-xl border border-border overflow-hidden">
            <DatasetGrid
              datasetId={id}
              columns={profile.data.columns}
              totalRows={dataset.data.rowCount}
            />
          </div>
        </motion.section>
      )}
    </main>
  );
}

/** Inline prompt + modal for an Excel dataset paused at the sheet-pick
 *  step. Opens the same picker the upload flow uses. Useful when the
 *  user dismissed the upload-time picker and is resuming from the
 *  datasets list. */
function AwaitingSheetPick({ dataset, onPicked }: { dataset: Dataset; onPicked: () => void }) {
  const [open, setOpen] = useState(true);
  const sheets = dataset.availableSheets ?? [];
  return (
    <>
      <div className="text-sm border border-amber-300/50 bg-amber-50/40 dark:bg-amber-900/20 rounded-lg p-4 space-y-2">
        <p className="font-medium">📑 Multi-sheet workbook — pick one to import</p>
        <p className="text-xs text-amber-800/80 dark:text-amber-200/80">
          Found {sheets.length} sheets in this Excel file. Pick which one to ingest;
          the file is already on the server, no re-upload needed.
        </p>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setOpen(true)}>
            📑 Pick sheet
          </Button>
        </div>
      </div>
      {open && (
        <SheetPickerModal
          dataset={dataset}
          onPicked={() => { setOpen(false); onPicked(); }}
          onCancel={() => setOpen(false)}
        />
      )}
    </>
  );
}

/** Same shape as AwaitingSheetPick but for the island-pick branch.
 *  Triggered when the chosen sheet contains 2+ disjoint data tables. */
function AwaitingIslandPick({ dataset, onPicked }: { dataset: Dataset; onPicked: () => void }) {
  const [open, setOpen] = useState(true);
  const islands = dataset.availableIslands ?? [];
  return (
    <>
      <div className="text-sm border border-amber-300/50 bg-amber-50/40 dark:bg-amber-900/20 rounded-lg p-4 space-y-2">
        <p className="font-medium">📐 Sheet has multiple data tables — pick which one to import</p>
        <p className="text-xs text-amber-800/80 dark:text-amber-200/80">
          Detected {islands.length} disjoint rectangles on{dataset.selectedSheet ? ` sheet "${dataset.selectedSheet}"` : " the sheet"}.
          Each one looks like a standalone table; pick the range you want as this dataset.
        </p>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setOpen(true)}>
            📐 Pick island
          </Button>
        </div>
      </div>
      {open && (
        <IslandPickerModal
          dataset={dataset}
          onPicked={() => { setOpen(false); onPicked(); }}
          onCancel={() => setOpen(false)}
        />
      )}
    </>
  );
}

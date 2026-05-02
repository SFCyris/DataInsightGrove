"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { DatasetGrid } from "@/components/grid/dataset-grid";
import { ProfileCard } from "@/components/profile/profile-card";
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
            <Button
              size="lg"
              disabled={dataset.data.status !== "ready" || shaping || shapeInPipeline.isPending}
              onClick={() => { setShaping(true); shapeInPipeline.mutate(); }}
              className="!bg-emerald-500 !text-emerald-950 hover:!bg-emerald-400"
              title="Create a new pipeline pre-attached to this dataset and open the editor"
            >
              {shaping || shapeInPipeline.isPending ? "✨ Opening…" : "✂️ Shape in a pipeline →"}
            </Button>
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

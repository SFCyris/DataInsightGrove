"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { buttonVariants } from "@/components/ui/button";
import { UploadDropzone } from "@/components/upload-dropzone";
import { DatasetCard } from "@/components/dataset-card";
import { HelpLink } from "@/components/help-link";

export default function DatasetsPage() {
  const reduce = useReducedMotion();
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: api.listDatasets,
    refetchInterval: (q) => {
      // Poll while any dataset is mid-ingest.
      const data = q.state.data;
      if (Array.isArray(data) && data.some((d) => d.status === "ingesting")) return 1500;
      return false;
    },
  });

  const fadeUp = reduce
    ? { initial: false, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 32 },
      };

  return (
    <main id="main" className="flex flex-1 flex-col p-8 gap-8 max-w-6xl w-full mx-auto">
      <motion.header {...fadeUp} className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl select-none" role="img" aria-label="Grove">
            🌳
          </span>
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground">
              DIG
            </p>
            <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
              Datasets <HelpLink topic="Importing and managing datasets" anchor="2--ingest--drop-a-csv-or-use-a-sample" />
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/datasets/from-rest"
            className={buttonVariants({ variant: "outline", size: "sm" })}
            title="Import from a REST API — auth, pagination, JSONPath"
          >
            🌐 From REST API
          </Link>
          <Link
            href="/connectors/new"
            className={buttonVariants({ variant: "outline", size: "sm" })}
            title="AI: generate a connector folder from a URL"
          >
            ✨ Generate connector
          </Link>
          <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            ← Home
          </Link>
        </div>
      </motion.header>

      <UploadDropzone />

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            <span className="mr-1">📚</span> Library
          </h2>
          <span className="text-xs text-muted-foreground tabular-nums">
            {datasets.data?.length ?? 0} dataset{datasets.data?.length === 1 ? "" : "s"}
          </span>
        </div>

        {datasets.isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-28 rounded-xl bg-muted/40 animate-pulse" />
            ))}
          </div>
        )}

        {datasets.data && datasets.data.length === 0 && (
          <motion.div
            {...fadeUp}
            className="text-center py-16 text-sm text-muted-foreground"
          >
            <div className="text-5xl mb-3 select-none" aria-hidden>
              🪴
            </div>
            No datasets yet — drop a CSV above to get started.
          </motion.div>
        )}

        {datasets.data && datasets.data.length > 0 && (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 list-none">
            {datasets.data.map((d, i) => (
              <DatasetCard key={d.id} d={d} index={i} />
            ))}
          </ul>
        )}

        {datasets.error && (
          <p className="text-sm text-destructive">
            ❌ Error loading datasets: {(datasets.error as Error).message}
          </p>
        )}
      </section>
    </main>
  );
}

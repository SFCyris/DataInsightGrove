"use client";

import Link from "next/link";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { UploadDropzone } from "@/components/upload-dropzone";
import { ReferenceFileModal } from "@/components/reference-file-modal";
import { DatasetCard } from "@/components/dataset-card";
import { HelpLink } from "@/components/help-link";
import {
  LibraryToolbar,
  filterAndSortLibrary,
  useLibraryView,
} from "@/components/library-toolbar";
import { useDocumentTitle } from "@/lib/use-document-title";

export default function DatasetsPage() {
  useDocumentTitle('Datasets');
  const reduce = useReducedMotion();
  const [refModalOpen, setRefModalOpen] = useState(false);
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
  const libView = useLibraryView("dig.datasets.libraryView");
  const visibleDatasets = datasets.data
    ? filterAndSortLibrary(datasets.data, libView)
    : [];

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
          {/* Back/home is always at top-left for consistency. */}
          <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            ← Home
          </Link>
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
          <Button
            size="sm"
            variant="outline"
            onClick={() => setRefModalOpen(true)}
            title="Reference an existing file on the DIG server (no copy is made; the file stays where it is)"
          >
            📁 Reference file
          </Button>
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
        </div>
      </motion.header>

      <UploadDropzone />
      <ReferenceFileModal
        open={refModalOpen}
        onClose={() => setRefModalOpen(false)}
      />

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          <span className="mr-1">📚</span> Library
        </h2>

        {datasets.data && datasets.data.length > 0 && (
          <LibraryToolbar
            view={libView}
            totalCount={datasets.data.length}
            resultCount={visibleDatasets.length}
            itemNoun="dataset"
          />
        )}

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

        {datasets.data && datasets.data.length > 0 && visibleDatasets.length === 0 && (
          <div className="text-center py-12 text-sm text-muted-foreground">
            <div className="text-3xl mb-2 select-none" aria-hidden>🔍</div>
            No datasets match <code className="px-1.5 py-0.5 rounded bg-muted">{libView.query}</code>.
            <button
              type="button"
              onClick={() => libView.setQuery("")}
              className="ml-2 underline hover:no-underline"
            >
              Clear
            </button>
          </div>
        )}

        {datasets.data && visibleDatasets.length > 0 && (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 list-none">
            {visibleDatasets.map((d, i) => (
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

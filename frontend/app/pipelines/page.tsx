"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useDropzone } from "react-dropzone";
import { api } from "@/lib/api/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { TemplatesDialog } from "@/components/templates-dialog";
import { HelpLink } from "@/components/help-link";
import { PipelineCard } from "@/components/pipeline-card";
import {
  LibraryToolbar,
  filterAndSortLibrary,
  useLibraryView,
} from "@/components/library-toolbar";

export default function PipelinesPage() {
  const reduce = useReducedMotion();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [templatesOpen, setTemplatesOpen] = useState(false);

  const list = useQuery({ queryKey: ["pipelines"], queryFn: api.listPipelines });
  const libView = useLibraryView("dig.pipelines.libraryView");
  const visiblePipelines = list.data
    ? filterAndSortLibrary(list.data, libView)
    : [];

  const create = useMutation({
    mutationFn: (n: string) => api.createPipeline(n),
    onSuccess: (p) => {
      toast.success(`✨ Created "${name || "pipeline"}"`);
      queryClient.invalidateQueries({ queryKey: ["pipelines"] });
      router.push(`/pipelines/${p.id}`);
    },
    onError: (e: Error) => toast.error(`Create failed: ${e.message}`),
  });

  const importMut = useMutation({
    mutationFn: async (file: File) => {
      const text = await file.text();
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch (e) {
        throw new Error(`Not valid JSON: ${(e as Error).message}`);
      }
      return api.importPipeline(parsed);
    },
    onSuccess: (p) => {
      toast.success(`📥 Imported "${p.document.name ?? "pipeline"}"`);
      queryClient.invalidateQueries({ queryKey: ["pipelines"] });
      router.push(`/pipelines/${p.id}`);
    },
    onError: (e: Error) => toast.error(`Import failed: ${e.message}`),
  });

  const onDrop = useCallback(
    (files: File[]) => {
      if (files[0]) importMut.mutate(files[0]);
    },
    [importMut],
  );
  const dropzone = useDropzone({
    onDrop,
    accept: { "application/json": [".json", ".dig.json"] },
    multiple: false,
    noClick: true,
    noKeyboard: true,
  });

  const fadeUp = reduce
    ? { initial: false, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 },
      };

  return (
    <main
      {...dropzone.getRootProps({
        className: [
          "flex flex-1 flex-col p-8 gap-8 max-w-6xl w-full mx-auto relative",
          dropzone.isDragActive ? "outline outline-2 outline-emerald-400/60 outline-offset-[-12px] rounded-2xl" : "",
        ].join(" "),
      })}
    >
      <input {...dropzone.getInputProps()} />
      {dropzone.isDragActive && (
        <div className="absolute inset-4 z-30 grid place-items-center bg-emerald-500/10 backdrop-blur-sm rounded-2xl pointer-events-none">
          <div className="text-center">
            <div className="text-5xl mb-2">📥</div>
            <p className="font-medium">Drop a .dig.json to import</p>
          </div>
        </div>
      )}
      <motion.header {...fadeUp} className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Back/home is always at top-left for consistency. */}
          <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>← Home</Link>
          <span className="text-2xl select-none" role="img" aria-label="Grove">🌳</span>
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground">DIG</p>
            <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
              Pipelines <HelpLink topic="Building and running pipelines" anchor="3--shape--build-a-pipeline" />
            </h1>
          </div>
        </div>
      </motion.header>

      <motion.section
        {...fadeUp}
        transition={{ ...("transition" in fadeUp ? fadeUp.transition : {}), delay: 0.05 }}
        className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3"
      >
        <div className="rounded-xl border border-border bg-card p-4 flex items-center gap-3">
          <span className="text-xl select-none" aria-hidden>🧪</span>
          <input
            type="text"
            placeholder="Name a new pipeline…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && name.trim()) create.mutate(name.trim());
            }}
            className="flex-1 bg-transparent outline-none text-sm border-b border-transparent focus:border-foreground/30 transition-colors py-1"
          />
          <Button
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate(name.trim())}
          >
            {create.isPending ? "⏳ Creating…" : "➕ Blank"}
          </Button>
        </div>

        <button
          type="button"
          onClick={() => setTemplatesOpen(true)}
          className="rounded-xl border border-dashed border-emerald-300/40 bg-emerald-500/5 hover:bg-emerald-500/10 p-4 flex items-center gap-3 text-left transition-colors"
        >
          <span className="text-xl select-none" aria-hidden>📦</span>
          {/* Phrasing-only children inside <button>. */}
          <span className="min-w-0 inline-flex flex-col items-start">
            <span className="block text-sm font-medium">Browse templates</span>
            <span className="block text-[11px] text-muted-foreground">
              Start from a worked example
            </span>
          </span>
          <span className="text-muted-foreground/60 ml-1">→</span>
        </button>

        <button
          type="button"
          onClick={dropzone.open}
          className="rounded-xl border border-dashed border-border hover:border-foreground/30 bg-card hover:bg-muted/30 p-4 flex items-center gap-3 text-left transition-colors"
        >
          <span className="text-xl select-none" aria-hidden>📥</span>
          <span className="min-w-0 inline-flex flex-col items-start">
            <span className="block text-sm font-medium">Import .dig.json</span>
            <span className="block text-[11px] text-muted-foreground">
              {importMut.isPending ? "Importing…" : "Or drop the file anywhere"}
            </span>
          </span>
          <span className="text-muted-foreground/60 ml-1">→</span>
        </button>
      </motion.section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-xs uppercase tracking-widest text-muted-foreground shrink-0">
            📚 Library
          </h2>
        </div>
        {list.data && list.data.length > 0 && (
          <LibraryToolbar
            view={libView}
            totalCount={list.data.length}
            resultCount={visiblePipelines.length}
            itemNoun="pipeline"
          />
        )}
        {list.isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[0,1,2].map(i => (<div key={i} className="h-20 rounded-xl bg-muted/40 animate-pulse" />))}
          </div>
        )}
        {list.data && list.data.length === 0 && (
          <div className="text-center py-12 text-sm text-muted-foreground">
            <div className="text-5xl mb-3 select-none" aria-hidden>🛤</div>
            <p className="max-w-md mx-auto mb-3">
              No pipelines yet. Name one above and start shaping data,
              or seed the workspace with four demo pipelines you can
              poke at.
            </p>
            <a
              href="/?tour=replay"
              className="inline-block text-xs px-3 py-1.5 rounded-md border border-border hover:bg-muted"
              title="Replay the welcome tour from the home page"
            >
              🧭 Replay welcome tour
            </a>
          </div>
        )}
        {list.data && list.data.length > 0 && visiblePipelines.length === 0 && (
          <div className="text-center py-12 text-sm text-muted-foreground">
            <div className="text-3xl mb-2 select-none" aria-hidden>🔍</div>
            No pipelines match <code className="px-1.5 py-0.5 rounded bg-muted">{libView.query}</code>.
            <button
              type="button"
              onClick={() => libView.setQuery("")}
              className="ml-2 underline hover:no-underline"
            >
              Clear
            </button>
          </div>
        )}
        {list.data && visiblePipelines.length > 0 && (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 list-none">
            {visiblePipelines.map((p, i) => (
              <PipelineCard key={p.id} p={p} index={i} />
            ))}
          </ul>
        )}
      </section>

      <TemplatesDialog open={templatesOpen} onClose={() => setTemplatesOpen(false)} />
    </main>
  );
}

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

export default function PipelinesPage() {
  const reduce = useReducedMotion();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [templatesOpen, setTemplatesOpen] = useState(false);

  const list = useQuery({ queryKey: ["pipelines"], queryFn: api.listPipelines });

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
          <span className="text-2xl select-none" role="img" aria-label="Grove">🌳</span>
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground">DIG</p>
            <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
              Pipelines <HelpLink topic="Building and running pipelines" anchor="3--shape--build-a-pipeline" />
            </h1>
          </div>
        </div>
        <Link href="/" className={buttonVariants({ variant: "ghost" })}>← Home</Link>
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
        <h2 className="text-xs uppercase tracking-widest text-muted-foreground">
          📚 Library
        </h2>
        {list.isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[0,1,2].map(i => (<div key={i} className="h-20 rounded-xl bg-muted/40 animate-pulse" />))}
          </div>
        )}
        {list.data && list.data.length === 0 && (
          <div className="text-center py-12 text-sm text-muted-foreground">
            <div className="text-5xl mb-3 select-none" aria-hidden>🛤</div>
            No pipelines yet. Name one above and start shaping data.
          </div>
        )}
        {list.data && list.data.length > 0 && (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 list-none">
            {list.data.map((p, i) => (
              <motion.li
                key={p.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ type: "spring", stiffness: 320, damping: 30, delay: 0.04 * i }}
              >
                <Link
                  href={`/pipelines/${p.id}`}
                  className="block p-4 rounded-xl border border-border bg-card hover:border-foreground/30 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">🛤</span>
                    <p className="font-medium truncate flex-1">{p.name}</p>
                  </div>
                  <dl className="grid grid-cols-3 gap-2 text-xs text-muted-foreground tabular-nums">
                    <div>
                      <dt className="opacity-60 uppercase tracking-wider">Datasets</dt>
                      <dd className="font-medium text-foreground">{p.datasetCount}</dd>
                    </div>
                    <div>
                      <dt className="opacity-60 uppercase tracking-wider">Steps</dt>
                      <dd className="font-medium text-foreground">{p.nodeCount}</dd>
                    </div>
                    <div>
                      <dt className="opacity-60 uppercase tracking-wider">Outputs</dt>
                      <dd className="font-medium text-foreground">{p.outputCount}</dd>
                    </div>
                  </dl>
                </Link>
              </motion.li>
            ))}
          </ul>
        )}
      </section>

      <TemplatesDialog open={templatesOpen} onClose={() => setTemplatesOpen(false)} />
    </main>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, API_BASE } from "@/lib/api/client";
import { buttonVariants, Button } from "@/components/ui/button";
import { MatrixTreeBackground } from "@/components/matrix-tree-background";
import { NumberTree3D } from "@/components/number-tree-3d";
import { Tour, type TourStep } from "@/components/tour/tour";
import { ThemeToggle } from "@/components/theme-toggle";

const WORKFLOW: Array<{
  n: string;
  emoji: string;
  title: string;
  body: string;
  href: string;
  cta: string;
}> = [
  {
    n: "1",
    emoji: "📥",
    title: "Ingest",
    body: "Drop in a CSV. DIG profiles every column — types, nulls, distincts, distributions — so you know what you're working with.",
    href: "/datasets",
    cta: "Open Datasets",
  },
  {
    n: "2",
    emoji: "✂️",
    title: "Shape",
    body: "Build a pipeline: a DAG of steps that filter, derive, join, aggregate. Add a step from the library, see the schema flow.",
    href: "/pipelines",
    cta: "Open Pipelines",
  },
  {
    n: "3",
    emoji: "▶️",
    title: "Run",
    body: "Preview on a sample in your browser (DuckDB-WASM, instant) — or run on the backend over the full dataset and write Parquet.",
    href: "/pipelines",
    cta: "Run a pipeline",
  },
];

export default function Home() {
  const reduce = useReducedMotion();
  const router = useRouter();
  const [tourOpen, setTourOpen] = useState(false);

  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.listDatasets });
  const pipelines = useQuery({ queryKey: ["pipelines"], queryFn: api.listPipelines });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 30_000 });

  // Derive the displayed ports from the actual API base + the page's own
  // origin. No hardcoded defaults — if the user reconfigures via
  // `start.sh --api-port N --save` everything just reflects it.
  //
  // apiPort is safe to compute during SSR: API_BASE comes from the
  // NEXT_PUBLIC_DIG_API env var which Next.js bakes into the bundle at
  // build time, so the value is identical on server and client.
  const apiPort = (() => {
    try { return new URL(API_BASE).port || (new URL(API_BASE).protocol === "https:" ? "443" : "80"); }
    catch { return "?"; }
  })();
  // webPort is not — `window` doesn't exist during SSR. We start with a
  // placeholder that matches what the server renders, then fill in the
  // real value after mount. This keeps the first client render byte-
  // identical to the server output (no hydration mismatch) and updates
  // a tick later to show the actual port.
  const [webPort, setWebPort] = useState<string>("…");
  useEffect(() => {
    setWebPort(
      window.location.port ||
      (window.location.protocol === "https:" ? "443" : "80"),
    );
  }, []);

  // Suggest the tour for first-time visitors.
  useEffect(() => {
    try {
      if (!localStorage.getItem("dig.tour.home")) {
        // Auto-open tour after a short pause so the matrix backdrop shows first.
        const t = setTimeout(() => setTourOpen(true), 700);
        return () => clearTimeout(t);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const importSample = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/datasets/samples/import`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    },
    onSuccess: (d) => {
      toast.success(`🌱 Sample imported (${d.rowCount?.toLocaleString() ?? "?"} rows). Opening…`);
      router.push(`/datasets/${d.id}`);
    },
    onError: (e: Error) => toast.error(`Sample import failed: ${e.message}`),
  });

  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 12 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 32 },
      };

  const tourSteps: TourStep[] = [
    {
      title: "Welcome to DataInsightGrove 🌳",
      body: (
        <>
          DIG turns messy data into shape in three moves. This tour takes about 60 seconds.
          Skip anytime.
        </>
      ),
      nextLabel: "Show me →",
    },
    {
      title: "Three moves, in order",
      body: (
        <>
          <strong>Ingest → Shape → Run.</strong> The cards below mirror that flow.
          Most workflows start at #1 and end at #3.
        </>
      ),
      target: '[data-tour="workflow"]',
      placement: "bottom",
    },
    {
      title: "Get started instantly",
      body: (
        <>
          Don&apos;t have a CSV handy? Click <strong>🌱 Try with sample data</strong> and DIG
          will import a small demo dataset and open it for you.
        </>
      ),
      target: '[data-tour="sample-cta"]',
      placement: "top",
    },
    {
      title: "What you&apos;ll see next",
      body: (
        <>
          The dataset page shows a fast, scrollable grid plus profile cards above each
          column (histograms, null %, top values). After that, hop to <strong>🛤 Pipelines</strong>
          to build a transform pipeline.
        </>
      ),
      target: '[data-tour="open-app"]',
      placement: "top",
      nextLabel: "Got it",
    },
    {
      title: "You&apos;re ready",
      body: (
        <>
          You can replay this tour from the <strong>Help</strong> link at the bottom.
          For the full reference, see <code>docs/getting_started.md</code>.
        </>
      ),
      nextLabel: "Let&apos;s go ✓",
    },
  ];

  return (
    <>
      {/* Layered backdrops, back-to-front:
            -z-30  base black/emerald gradient (always there)
            -z-25  NumberTree3D    — slow-rotating muted-green digit tree (depth)
            -z-10  MatrixTreeBackground  — cascading rain inside tree silhouette
            -z-[5] radial darken overlay (below) — keeps text legible
      */}
      <div
        className="fixed inset-0 -z-30 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at 50% 60%, #06150f 0%, #020907 60%, #000 100%)",
        }}
        aria-hidden
      />
      <NumberTree3D className="fixed inset-0 -z-[25] pointer-events-none" />
      {/* `dimmed` while sample-import in flight: calms the rain so the
          ⏳ Importing... button gets visual focus and the page doesn't
          feel like nothing happened on click. */}
      <MatrixTreeBackground dimmed={importSample.isPending} />
      {/* Translucent overlay so text stays readable over the matrix backdrop */}
      <div
        className="fixed inset-0 -z-[5] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.78) 70%, rgba(0,0,0,0.92) 100%)",
        }}
        aria-hidden
      />

      <main id="main" className="flex flex-1 items-center justify-center p-4 sm:p-8 relative z-0">
        <div className="max-w-5xl w-full flex flex-col gap-10 text-zinc-100">
          {/* Hero */}
          <motion.header {...fadeUp} className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <span className="text-3xl select-none" role="img" aria-label="Grove">🌳</span>
              <p className="text-xs uppercase tracking-[0.25em] text-emerald-300/70">
                DataInsightGrove<sup className="ml-0.5 text-[0.6em] tracking-normal" aria-label="trademark">™</sup>
                <span className="mx-1.5 text-emerald-300/40">·</span>
                {/* Pulled from the live /health endpoint via the same query
                    the footer uses, so the version always tracks the running
                    backend instead of a hand-typed string drifting over time. */}
                v{health.data?.version ?? "—"}
              </p>
            </div>
            <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight leading-[1.05]">
              DataInsight Grove<br />
              <span className="text-emerald-200/80">Data preparation for the rest of us.</span>
            </h1>
          </motion.header>

          {/* Workflow cards */}
          <motion.section
            {...fadeUp}
            transition={{ ...("transition" in fadeUp ? fadeUp.transition : {}), delay: 0.08 }}
            data-tour="workflow"
            className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4"
          >
            {WORKFLOW.map((w, i) => (
              <motion.div
                key={w.n}
                initial={reduce ? false : { opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  type: "spring",
                  stiffness: 280,
                  damping: 26,
                  delay: 0.15 + i * 0.08,
                }}
                className="rounded-xl border border-emerald-300/15 bg-zinc-950/55 backdrop-blur-md p-5 flex flex-col gap-3 hover:border-emerald-300/40 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full grid place-items-center bg-emerald-500/10 border border-emerald-300/20 text-emerald-200 font-semibold tabular-nums text-sm">
                    {w.n}
                  </div>
                  <span className="text-2xl select-none" aria-hidden>{w.emoji}</span>
                  <h2 className="text-lg font-semibold">{w.title}</h2>
                </div>
                <p className="text-sm text-zinc-300/80 leading-relaxed flex-1">{w.body}</p>
                <Link
                  href={w.href}
                  className="text-xs text-emerald-300 hover:text-emerald-200 self-start mt-1"
                >
                  {w.cta} →
                </Link>
              </motion.div>
            ))}
          </motion.section>

          {/* CTAs */}
          <motion.section
            {...fadeUp}
            transition={{ ...("transition" in fadeUp ? fadeUp.transition : {}), delay: 0.32 }}
            className="flex flex-col sm:flex-row gap-3 items-center"
          >
            <Button
              size="lg"
              data-tour="sample-cta"
              onClick={() => importSample.mutate()}
              disabled={importSample.isPending}
              className="!bg-emerald-500 !text-emerald-950 hover:!bg-emerald-400"
            >
              {importSample.isPending ? "⏳ Importing…" : "🌱 Try with sample data"}
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={() => setTourOpen(true)}
              className="!bg-transparent !border-emerald-500/60 !text-emerald-700 dark:!text-emerald-200 hover:!bg-emerald-500/10 dark:hover:!bg-emerald-500/15"
            >
              🧭 Take the 60-second tour
            </Button>
            <div className="hidden sm:block flex-1" />
            <div data-tour="open-app" className="flex gap-2">
              <Link
                href="/datasets"
                className={
                  buttonVariants({ variant: "ghost", size: "lg" }) +
                  " !text-zinc-200 hover:!bg-emerald-500/10"
                }
              >
                📊 Datasets
                {datasets.data && (
                  <span className="ml-1 text-[10px] text-emerald-300/70 tabular-nums">
                    {datasets.data.length}
                  </span>
                )}
              </Link>
              <Link
                href="/pipelines"
                className={
                  buttonVariants({ variant: "ghost", size: "lg" }) +
                  " !text-zinc-200 hover:!bg-emerald-500/10"
                }
              >
                🛤 Pipelines
                {pipelines.data && (
                  <span className="ml-1 text-[10px] text-emerald-300/70 tabular-nums">
                    {pipelines.data.length}
                  </span>
                )}
              </Link>
              <Link
                href="/gallery"
                className={
                  buttonVariants({ variant: "ghost", size: "lg" }) +
                  " !text-zinc-200 hover:!bg-emerald-500/10"
                }
              >
                🌳 Gallery
              </Link>
            </div>
          </motion.section>

          {/* Footer */}
          <motion.footer
            {...fadeUp}
            transition={{ ...("transition" in fadeUp ? fadeUp.transition : {}), delay: 0.4 }}
            className="text-xs text-zinc-400/70 pt-6 border-t border-emerald-300/10 flex flex-wrap items-center gap-x-4 gap-y-1"
          >
            <span>v{health.data?.version ?? "—"}</span>
            <span>·</span>
            <span>backend on :{apiPort}</span>
            <span>·</span>
            <span>web on :{webPort}</span>
            <span className="flex-1" />
            <ThemeToggle compact />
            {/* Tell first-time users the command palette exists. ⌘K is the
                fastest way to jump anywhere; without this hint it's invisible. */}
            <span
              className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-border/40 text-[10px]"
              title="Open the command palette to jump to any page or run any action"
            >
              <kbd className="font-mono">⌘K</kbd>
              <span className="text-muted-foreground/80">palette</span>
            </span>
            <button
              type="button"
              onClick={() => setTourOpen(true)}
              className="hover:text-emerald-200 transition-colors"
            >
              🧭 Help · replay tour
            </button>
            <Link href="/settings" className="hover:text-emerald-200 transition-colors">
              ⚙️ Settings
            </Link>
            <a
              href={`${API_BASE}/docs`}
              target="_blank"
              rel="noreferrer"
              className="hover:text-emerald-200 transition-colors"
            >
              📡 API
            </a>
            <a
              href="https://github.com/SFCyris/DataInsightGrove"
              target="_blank"
              rel="noreferrer"
              className="hover:text-emerald-200 transition-colors"
              title="Source on GitHub (AGPL-3.0)"
            >
              🐙 Source
            </a>
          </motion.footer>
        </div>
      </main>

      <Tour
        steps={tourSteps}
        open={tourOpen}
        onClose={() => setTourOpen(false)}
        storageKey="dig.tour.home"
      />
    </>
  );
}

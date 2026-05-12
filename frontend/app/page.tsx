"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, API_BASE, API_TOKEN } from "@/lib/api/client";
import { useApiBase } from "@/lib/use-api-base";
import { fmtVersion } from "@/lib/format-version";
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
  // Hydration-safe API base for rendering into the footer link.
  // Using API_BASE directly would mismatch between SSR (no `window`)
  // and CSR (resolves from window.location), tripping React's
  // hydration check.
  const apiBaseRendered = useApiBase();

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

  // "🌱 Try with sample data" — the dominant first-run path. We deliberately
  // chain ingest → auto-pipeline → editor so a brand-new user lands on a
  // *rendered chart* within seconds, not on a column grid that looks like
  // any other table viewer. The PLG-loss risk for a self-hosted data tool
  // is steepest at the moment between "I installed it" and "I made
  // something" — collapse that to one click.
  //
  // The button now seeds four demo pipelines side-by-side via the
  // backend's /pipelines/seed-demo endpoint:
  //   1. customers overview — 1-3 chart pipeline (the original first-run UX)
  //   2. healthcare clinical analysis — 5 datasets, 30+ steps, 5 charts
  //   3. housing market — 4 datasets, 15+ steps, 5 charts + interactive map
  // The frontend redirects to the customers overview as before so the
  // first-stop is still a chart, not a 30-node DAG. The other two
  // pipelines surface in the pipeline list + run history.
  type SeedResult = {
    primary: { datasetId: string; pipelineId: string };
    pipelines: Array<{ id: string; name: string; chartCount: number }>;
    totalCharts: number;
  };

  type SeedConflict = {
    code: "demo_pipelines_exist";
    existing: string[];
    message: string;
  };

  const importSample = useMutation({
    mutationFn: async ({ overwrite = false }: { overwrite?: boolean } = {}): Promise<SeedResult> => {
      // Direct fetch (not the typed wrapper) so we have to attach the
      // Bearer token ourselves — without it, --global mode rejects with
      // 401 and the user sees a generic "NetworkError" toast. Caught the
      // hard way during Pop!_OS LAN testing.
      const headers: Record<string, string> = { Accept: "application/json" };
      if (API_TOKEN) headers.Authorization = `Bearer ${API_TOKEN}`;

      const url = `${API_BASE}/pipelines/seed-demo${overwrite ? "?overwrite=true" : ""}`;
      const res = await fetch(url, { method: "POST", headers });

      if (res.status === 409) {
        // Demo pipelines already exist. The backend hands us the names so
        // we can ask the user, by name, whether to overwrite. Doing this
        // outside `mutationFn` keeps the React Query state machine simple
        // — the confirm dialog short-circuits via a thrown error and we
        // re-mutate from the dialog handler with overwrite=true.
        let detail: SeedConflict | null = null;
        try {
          const j = (await res.json()) as { detail?: SeedConflict | string };
          if (typeof j.detail === "object" && j.detail) detail = j.detail as SeedConflict;
        } catch {
          /* fall through */
        }
        if (detail && detail.code === "demo_pipelines_exist") {
          // Stop the mutation cleanly with a payload the onError handler
          // can read (Error.cause is the standard escape hatch for this).
          const err = new Error("demo pipelines already exist");
          (err as Error & { conflict?: SeedConflict }).conflict = detail;
          throw err;
        }
        throw new Error(`${res.status} ${res.statusText}`);
      }
      if (!res.ok) {
        let detail: string | null = null;
        try {
          const j = (await res.json()) as { detail?: string };
          detail = j.detail ?? null;
        } catch {
          /* ignore */
        }
        throw new Error(detail ?? `${res.status} ${res.statusText}`);
      }
      return (await res.json()) as SeedResult;
    },
    onSuccess: (result) => {
      const titles = result.pipelines.map((p) => p.name).join(" · ");
      toast.success(
        `🌱 ${result.pipelines.length} demos ready — ${result.totalCharts} charts`,
        { description: titles },
      );
      router.push(`/pipelines/${result.primary.pipelineId}`);
    },
    onError: (e: Error) => {
      const conflict = (e as Error & { conflict?: SeedConflict }).conflict;
      if (conflict) {
        // Sonner-based confirm — non-blocking (doesn't freeze the JS
        // thread the way window.confirm does), themed with the rest of
        // the UI, and screenshots cleanly in headless test runs. Action
        // button overwrites; cancel button keeps the existing demos.
        toast(
          `🌱 Demos already seeded · overwrite ${conflict.existing.length} pipeline${conflict.existing.length === 1 ? "" : "s"}?`,
          {
            description: conflict.existing.map((n) => `· ${n}`).join("  "),
            duration: 12_000,
            action: {
              label: "Overwrite",
              onClick: () => importSample.mutate({ overwrite: true }),
            },
            cancel: {
              label: "Keep them",
              onClick: () =>
                toast.info("👍 Existing demos kept. Open the Pipelines list to use them."),
            },
          },
        );
        return;
      }
      toast.error(`Sample import failed: ${e.message}`);
    },
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
      // Anchor the welcome step to the hero so it feels grounded — round-3
      // UX finding: previously the modal floated mid-page with nothing
      // visually connecting it to the page beneath, which read as a
      // bug the first time you saw it.
      target: '[data-tour="hero"]',
      placement: "bottom",
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
      title: "What you'll see next",
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
      title: "You're ready",
      body: (
        <>
          You can replay this tour from the <strong>Help</strong> link at the bottom.
          For the full reference, see <code>docs/getting_started.md</code>.
        </>
      ),
      nextLabel: "Let's go ✓",
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
          <motion.header {...fadeUp} data-tour="hero" className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <span className="text-3xl select-none" role="img" aria-label="Grove">🌳</span>
              <p className="text-xs uppercase tracking-[0.25em] text-emerald-300/70">
                DataInsightGrove<sup className="ml-0.5 text-[0.6em] tracking-normal" aria-label="trademark">™</sup>
                <span className="mx-1.5 text-emerald-300/40">·</span>
                {/* Pulled from the live /health endpoint via the same query
                    the footer uses, so the version always tracks the running
                    backend instead of a hand-typed string drifting over time. */}
                v{fmtVersion(health.data?.version)}
              </p>
            </div>
            {/* h1 is the product name only; the tagline is a separate
                <p> with the same visual weight but distinct semantics so
                screen readers don't read them as one continuous heading
                (round-3 UX/a11y finding). */}
            <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight leading-[1.05]">
              DataInsight Grove
            </h1>
            <p className="text-4xl sm:text-5xl font-semibold tracking-tight leading-[1.05] text-emerald-200/80">
              Data preparation for the rest of us.
            </p>
          </motion.header>

          {/* First-run zero-state nudge: shown only when the user has no
              datasets and no pipelines yet. Promotes the chained sample
              import + auto-pipeline path so the first click ends in a
              live chart, not an empty editor. The data queries gate this
              on actual API state (not a localStorage flag) so wiping data
              re-summons the welcome — the right behaviour for a fresh
              install or a data reset. */}
          {datasets.data && datasets.data.length === 0 && pipelines.data && pipelines.data.length === 0 && (
            <motion.section
              {...fadeUp}
              transition={{ ...("transition" in fadeUp ? fadeUp.transition : {}), delay: 0.05 }}
              className="rounded-xl border border-emerald-400/40 bg-gradient-to-br from-emerald-500/10 via-emerald-500/5 to-transparent backdrop-blur-md p-5 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4"
            >
              <div className="text-4xl sm:text-5xl select-none shrink-0" aria-hidden>👋</div>
              <div className="flex-1 min-w-0">
                <p className="text-base sm:text-lg font-semibold text-emerald-100">
                  Welcome — your first four demos, one click away.
                </p>
                <p className="text-xs sm:text-sm text-emerald-200/80 leading-relaxed mt-1">
                  DIG will seed four demos: a one-click 📊 customers overview, a 🏥 healthcare clinical pipeline (5 datasets, 30+ steps), a 🏘 housing pipeline ending in an interactive 🗺 map, and a 📅 timestamped-report pipeline showcasing the new variable-templating surface. Your first stop is a chart — not a blank canvas.
                </p>
              </div>
              <Button
                size="lg"
                onClick={() => importSample.mutate({})}
                disabled={importSample.isPending}
                className="!bg-emerald-500 !text-emerald-950 hover:!bg-emerald-400 shrink-0"
              >
                {importSample.isPending ? "⏳ Setting up…" : "🚀 Get started"}
              </Button>
            </motion.section>
          )}

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
              >
                {/* Whole card is the link — clicking anywhere navigates.
                    The CTA chevron stays as visual affordance but is not a
                    separate tab-stop. focus-visible ring + group-hover on
                    border so keyboard users still see what's selected. */}
                <Link
                  href={w.href}
                  className="group block h-full rounded-xl border border-emerald-300/15 bg-zinc-950/55 backdrop-blur-md p-5 flex flex-col gap-3 hover:border-emerald-300/60 hover:bg-zinc-950/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60 focus-visible:border-emerald-300/60"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full grid place-items-center bg-emerald-500/10 border border-emerald-300/20 text-emerald-200 font-semibold tabular-nums text-sm">
                      {w.n}
                    </div>
                    <span className="text-2xl select-none" aria-hidden>{w.emoji}</span>
                    <h2 className="text-lg font-semibold">{w.title}</h2>
                  </div>
                  <p className="text-sm text-zinc-300/80 leading-relaxed flex-1">{w.body}</p>
                  <span
                    className="text-xs text-emerald-300 group-hover:text-emerald-200 self-start mt-1 transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  >
                    {w.cta} →
                  </span>
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
              onClick={() => importSample.mutate({})}
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
                href="/runs"
                className={
                  buttonVariants({ variant: "ghost", size: "lg" }) +
                  " !text-zinc-200 hover:!bg-emerald-500/10"
                }
              >
                📜 Run history
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
            <span>v{fmtVersion(health.data?.version)}</span>
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
              href={`${apiBaseRendered}/docs`}
              target="_blank"
              rel="noreferrer"
              className="hover:text-emerald-200 transition-colors"
              suppressHydrationWarning
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

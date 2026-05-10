"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export default function GalleryDetailPage({ params }: PageProps) {
  const { slug } = use(params);
  const reduce = useReducedMotion();
  const router = useRouter();

  // Hydration-safe share URL — `window` only exists on the client, so
  // start empty (matching the server render) and patch in the real URL
  // after mount. The bare `typeof window !== "undefined" ? … : ""`
  // pattern at the input causes a hydration mismatch every render.
  const [shareUrl, setShareUrl] = useState("");
  useEffect(() => {
    setShareUrl(window.location.href);
  }, []);

  const q = useQuery({
    queryKey: ["gallery", slug],
    queryFn: () => api.getGalleryTemplate(slug),
  });

  const cloneM = useMutation({
    mutationFn: () => api.cloneGalleryTemplate(slug),
    onSuccess: ({ pipelineId }) => {
      toast.success("✅ Template forked into your pipelines");
      router.push(`/pipelines/${pipelineId}`);
    },
    onError: (e: Error) => toast.error(`Couldn't fork: ${e.message}`),
  });

  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 },
      };

  return (
    <main id="main" className="flex-1 overflow-y-auto">
      <motion.section {...fadeUp} className="mx-auto max-w-3xl p-8">
        <Link
          href="/gallery"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← Back to gallery
        </Link>

        {q.isLoading && (
          <p className="mt-6 text-sm text-muted-foreground">Loading…</p>
        )}
        {q.error && (
          <p className="mt-6 text-sm text-destructive">
            Couldn't load template: {(q.error as Error).message}
          </p>
        )}

        {q.data && (
          <article className="mt-4">
            <header className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {q.data.title}
                </h1>
                <p className="text-xs text-muted-foreground mt-1">
                  {q.data.authorHandle && <span>by @{q.data.authorHandle} · </span>}
                  {q.data.viewCount} view{q.data.viewCount === 1 ? "" : "s"}
                  {q.data.isCurated && <span className="ml-2 text-amber-600">⭐ Curated</span>}
                </p>
              </div>
              <Button
                size="sm"
                onClick={() => cloneM.mutate()}
                disabled={cloneM.isPending}
              >
                {cloneM.isPending ? "⏳ Forking…" : "⚡ Use this template"}
              </Button>
            </header>

            {q.data.summary && (
              <p className="mt-4 text-sm leading-relaxed">{q.data.summary}</p>
            )}

            <div className="mt-3 flex gap-2 flex-wrap">
              {q.data.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] px-1.5 py-0.5 rounded-full border border-border bg-card/50"
                >
                  {tag}
                </span>
              ))}
            </div>

            <section className="mt-8 rounded-lg border border-border bg-card/40 p-4">
              <h2 className="text-xs uppercase tracking-widest text-muted-foreground mb-3">
                What this template does
              </h2>
              <dl className="grid grid-cols-2 gap-y-2 gap-x-6 text-sm">
                <dt className="text-muted-foreground">Steps</dt>
                <dd className="tabular-nums">
                  {(q.data.document.nodes ?? []).length}
                </dd>
                <dt className="text-muted-foreground">Datasets</dt>
                <dd className="tabular-nums">
                  {(q.data.document.datasets ?? []).length}
                </dd>
                <dt className="text-muted-foreground">Outputs</dt>
                <dd className="tabular-nums">
                  {(q.data.document.outputs ?? []).length}
                </dd>
                <dt className="text-muted-foreground">Sample data bundled?</dt>
                <dd>{q.data.needsSampleDataset ? "Yes" : "No"}</dd>
              </dl>
            </section>

            <section className="mt-6">
              <h2 className="text-xs uppercase tracking-widest text-muted-foreground mb-2">
                🔗 Share this template
              </h2>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={shareUrl}
                  suppressHydrationWarning
                  className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-xs font-mono"
                  onClick={(e) => (e.target as HTMLInputElement).select()}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(window.location.href);
                      toast.success("📋 Link copied");
                    } catch {
                      toast.error("Clipboard blocked — copy manually.");
                    }
                  }}
                >
                  📋 Copy
                </Button>
              </div>
            </section>
          </article>
        )}
      </motion.section>
    </main>
  );
}

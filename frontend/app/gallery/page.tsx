"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import { api, type GalleryTemplate } from "@/lib/api/client";
import { fmtInt } from "@/lib/format-number";
import { useDocumentTitle } from "@/lib/use-document-title";
import { PositiveLoader } from "@/components/positive-loader";

/**
 * Public template gallery — discoverability surface for shareable pipelines.
 *
 * Reads from the local DIG instance's /templates endpoint, which lists
 * every template the user has saved + any curated set bundled in.
 */
export default function GalleryPage() {
  useDocumentTitle('Templates');
  const reduce = useReducedMotion();
  const [search, setSearch] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["gallery"],
    queryFn: () => api.listGalleryTemplates(),
  });

  const templates = q.data ?? [];

  const allTags = useMemo(() => {
    const tags = new Set<string>();
    for (const t of templates) for (const tag of t.tags || []) tags.add(tag);
    return [...tags].sort();
  }, [templates]);

  const filtered = useMemo(() => {
    let out = templates;
    if (activeTag) out = out.filter((t) => (t.tags || []).includes(activeTag));
    if (search.trim()) {
      const q = search.toLowerCase();
      out = out.filter(
        (t) =>
          t.title.toLowerCase().includes(q) ||
          (t.summary ?? "").toLowerCase().includes(q) ||
          (t.tags || []).some((x) => x.toLowerCase().includes(q)),
      );
    }
    return out;
  }, [templates, activeTag, search]);

  const featured = filtered.filter((t) => t.isCurated);
  const community = filtered.filter((t) => !t.isCurated);

  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 },
      };

  return (
    <main id="main" className="flex-1 overflow-y-auto">
      <motion.section {...fadeUp} className="mx-auto max-w-6xl p-8">
        <header className="mb-8 flex items-end justify-between gap-4">
          <div className="flex items-start gap-3">
            {/* Back/home is always at top-left for consistency. */}
            <Link
              href="/"
              className="text-xs text-muted-foreground hover:text-foreground mt-1"
            >
              ← Home
            </Link>
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground">DIG</p>
              <h1 className="text-3xl font-semibold tracking-tight">🌳 Template gallery</h1>
              <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
                Worked pipelines you can fork and run. Click any template to see it in detail; "Use this template" creates a fresh pipeline from it.
              </p>
            </div>
          </div>
        </header>

        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="🔍 Search templates…"
            aria-label="Search templates"
            className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/40"
          />
          <div className="flex gap-1.5 flex-wrap">
            <button
              type="button"
              onClick={() => setActiveTag(null)}
              aria-pressed={!activeTag}
              className={[
                "px-2.5 py-1 text-xs rounded-md border transition-colors",
                !activeTag
                  ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20 font-medium"
                  : "border-border hover:border-foreground/30",
              ].join(" ")}
            >
              All
            </button>
            {allTags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setActiveTag(tag === activeTag ? null : tag)}
                aria-pressed={tag === activeTag}
                className={[
                  "px-2.5 py-1 text-xs rounded-md border transition-colors",
                  tag === activeTag
                    ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20 font-medium"
                    : "border-border hover:border-foreground/30",
                ].join(" ")}
              >
                {tag}
              </button>
            ))}
          </div>
        </div>

        {q.isLoading && (
          <div className="py-8 grid place-items-center">
            <PositiveLoader variant="rendering" primary="Loading gallery…" size="md" showTimer={false} />
          </div>
        )}
        {q.error && (
          <p className="text-sm text-destructive">
            Couldn't load gallery: {(q.error as Error).message}
          </p>
        )}

        {q.data && filtered.length === 0 && (
          <div className="text-center py-16">
            <span className="text-5xl select-none" aria-hidden>📭</span>
            <p className="mt-3 text-sm text-muted-foreground">
              No templates yet. Build a pipeline and click "🔗 Share" to publish one.
            </p>
          </div>
        )}

        {featured.length > 0 && (
          <section className="mb-10">
            <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground mb-3">
              ⭐ Featured
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {featured.map((t) => (
                <TemplateCard key={t.id} t={t} />
              ))}
            </div>
          </section>
        )}

        {community.length > 0 && (
          <section>
            <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground mb-3">
              🌍 All templates ({fmtInt(community.length)})
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {community.map((t) => (
                <TemplateCard key={t.id} t={t} />
              ))}
            </div>
          </section>
        )}
      </motion.section>
    </main>
  );
}

function TemplateCard({ t }: { t: GalleryTemplate }) {
  return (
    <Link
      href={`/gallery/${t.slug}`}
      className="block rounded-lg border border-border bg-card/50 hover:bg-card hover:border-foreground/30 p-4 transition-colors group"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium text-sm leading-tight group-hover:underline underline-offset-2">
          {t.title}
        </h3>
        {t.isCurated && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-amber-300/60 bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            ⭐
          </span>
        )}
      </div>
      {t.summary && (
        <p className="mt-1.5 text-xs text-muted-foreground line-clamp-3 leading-relaxed">
          {t.summary}
        </p>
      )}
      <div className="mt-3 flex items-center gap-2 flex-wrap">
        {(t.tags || []).slice(0, 3).map((tag) => (
          <span
            key={tag}
            className="text-[10px] px-1.5 py-0.5 rounded-full border border-border bg-background/50"
          >
            {tag}
          </span>
        ))}
        <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
          {t.viewCount > 0 && `👁 ${fmtInt(t.viewCount)}`}
          {t.authorHandle && (
            <span className="ml-2">@{t.authorHandle}</span>
          )}
        </span>
      </div>
    </Link>
  );
}

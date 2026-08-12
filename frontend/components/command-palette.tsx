"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, searchApi } from "@/lib/api/client";
import {
  setSettings,
  useSettings,
  useExpertise,
  EXPERTISE_LABEL,
  type ExpertiseLevel,
} from "@/lib/settings";
import { fmtInt } from "@/lib/format-number";
import { getRecent, listFavorites } from "@/lib/recent-items";

interface Action {
  id: string;
  label: string;
  emoji?: string;
  hint?: string;
  /** Extra terms folded into the cmdk value for searching only — not
   *  rendered. Used for step aliases / tags so "merge" finds `join`. */
  searchHints?: string;
  group: string;
  run: () => void | Promise<void>;
}

/**
 * App-wide command palette. Opens with ⌘K (or Ctrl+K). Provides:
 *   - jump to dataset / pipeline
 *   - quick actions (toggle theme, replay tour, open settings, …)
 *   - search across registered steps (so you can recall what's available)
 */
export function CommandPalette() {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();
  const settings = useSettings();
  const expertise = useExpertise();
  const queryClient = useQueryClient();
  // Round-4 UX-3 #6 — focus-trap & restore.
  // dialogRef wraps the entire palette; the Tab handler walks its
  // focusables and rewraps Tab/Shift+Tab so focus can't escape into
  // the (visually-obscured) page underneath. previousFocusRef
  // remembers what was focused before the palette opened so Esc
  // returns the user to where they were — without this, closing
  // ⌘K dropped focus on document.body and Tab landed in the URL bar.
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.listDatasets, enabled: open });
  const pipelines = useQuery({ queryKey: ["pipelines"], queryFn: api.listPipelines, enabled: open });
  const stepsQ = useQuery({ queryKey: ["steps"], queryFn: api.listSteps, enabled: open, staleTime: 60_000 });
  // Workspace search runs in parallel: when the user
  // types a query, we hit /search to surface column-level matches the
  // local cmdk filter doesn't see (since columns aren't part of the
  // local action list). Debounced via the trimmed query as the key.
  const trimmed = query.trim();
  const wsSearch = useQuery({
    queryKey: ["wsSearch", trimmed],
    queryFn: () => searchApi.query(trimmed, 30),
    enabled: open && trimmed.length >= 2,
    staleTime: 30_000,
  });

  // Open / close keybindings + ⌘⇧E mode cycle
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Round-4 UX#1 finding: holding ⌘K used to toggle the palette
      // dozens of times via key-repeat. Ignore repeated keydowns so
      // one keypress = one toggle.
      if (e.repeat) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "e") {
        e.preventDefault();
        const order: ExpertiseLevel[] = ["beginner", "builder", "engineer"];
        const next = order[(order.indexOf(expertise.level) + 1) % order.length];
        expertise.setLevel(next);
        toast.success(`Mode: ${EXPERTISE_LABEL[next]}`);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, expertise]);

  // UX-3 #6 part 1 — capture/restore focus around the palette lifecycle.
  // When the palette opens we remember whatever was focused (usually
  // the trigger button or the canvas), and on close we put focus back
  // there. Without this, dismissing the modal lands focus on the body
  // and screen-reader users lose their place in the page.
  useEffect(() => {
    if (open) {
      previousFocusRef.current = (document.activeElement as HTMLElement) ?? null;
    } else if (previousFocusRef.current) {
      // Defer to the next tick so the AnimatePresence exit doesn't
      // race with the focus restore.
      const el = previousFocusRef.current;
      requestAnimationFrame(() => {
        try { el.focus(); } catch { /* element may have unmounted */ }
      });
      previousFocusRef.current = null;
    }
  }, [open]);

  // UX-3 #6 part 2 — Tab loop. Keeps Tab and Shift+Tab cycling within
  // the palette while it's open. We attach the listener to the
  // dialog element (added in the JSX below) and intercept Tab when
  // the next focus target would land outside.
  useEffect(() => {
    if (!open) return;
    const root = dialogRef.current;
    if (!root) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const focusables = root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    root.addEventListener("keydown", onKey);
    return () => root.removeEventListener("keydown", onKey);
  }, [open]);

  const actions: Action[] = useMemo(() => {
    const out: Action[] = [];
    out.push(
      {
        id: "go:home", group: "Go to", label: "Home", emoji: "🌳",
        run: () => router.push("/"),
      },
      {
        id: "go:datasets", group: "Go to", label: "Datasets", emoji: "📊",
        run: () => router.push("/datasets"),
      },
      {
        id: "go:pipelines", group: "Go to", label: "Pipelines", emoji: "🛤",
        run: () => router.push("/pipelines"),
      },
      {
        id: "go:runs", group: "Go to", label: "Run history", emoji: "📜",
        run: () => router.push("/runs"),
      },
      {
        id: "go:catalog", group: "Go to", label: "Catalog", emoji: "🗺",
        run: () => router.push("/catalog"),
      },
      {
        id: "go:settings", group: "Go to", label: "Settings", emoji: "⚙️",
        run: () => router.push("/settings"),
      },
      {
        id: "go:schedules", group: "Go to", label: "Schedules", emoji: "⏰",
        run: () => router.push("/schedules"),
      },
      // Round-5 W5: create-flow verbs missing entirely. Users had to
      // open the pipelines index and click the "+ New" button — ⌘K +
      // "new" should be the shortest path.
      {
        id: "act:new-pipeline", group: "Create", label: "New blank pipeline", emoji: "✨",
        run: async () => {
          try {
            const doc = await api.createPipeline("Untitled pipeline");
            router.push(`/pipelines/${doc.id}`);
          } catch (e) {
            toast.error(`Could not create pipeline: ${(e as Error).message}`);
          }
        },
      },
      {
        id: "act:new-from-template", group: "Create", label: "Browse templates", emoji: "📦",
        run: () => router.push("/gallery"),
      },
      {
        id: "act:upload-dataset", group: "Create", label: "Upload a dataset", emoji: "📥",
        run: () => router.push("/datasets"),
      },
      {
        id: "act:copy-link", group: "Actions",
        label: "Copy current page URL",
        emoji: "🔗",
        run: () => {
          try {
            navigator.clipboard.writeText(window.location.href);
            toast.success("Link copied");
          } catch {
            toast.error("Clipboard unavailable");
          }
        },
      },
      {
        id: "act:theme", group: "Actions",
        // Round-9 fix: previously the label rendered the literal word
        // "next" instead of the actual next theme value.
        label: (() => {
          const next = settings.theme === "system" ? "light" : settings.theme === "light" ? "dark" : "system";
          return `Theme: ${settings.theme} → ${next}`;
        })(),
        emoji: "🎨",
        run: () => {
          const next = settings.theme === "system" ? "light" : settings.theme === "light" ? "dark" : "system";
          setSettings({ theme: next });
          toast.success(`Theme: ${next}`);
        },
      },
      {
        id: "act:livepreview", group: "Actions",
        label: `Live preview: ${settings.livePreview ? "on" : "off"}`,
        emoji: "🦆",
        run: () => {
          setSettings({ livePreview: !settings.livePreview });
          toast.success(`Live preview ${!settings.livePreview ? "on" : "off"}`);
        },
      },
      {
        id: "act:samplesize", group: "Actions",
        label: `Sample size: ${fmtInt(settings.sampleRows)} (cycle)`,
        emoji: "🎲",
        hint: "10k → 50k → 100k → 500k",
        run: () => {
          const order = [10_000, 50_000, 100_000, 500_000];
          const idx = order.indexOf(settings.sampleRows);
          const next = order[(idx + 1) % order.length];
          setSettings({ sampleRows: next });
          toast.success(`Sample size: ${fmtInt(next)}`);
        },
      },
      {
        id: "act:replay-tour", group: "Actions",
        label: "Replay welcome tour",
        emoji: "🧭",
        run: () => {
          // Match the Settings → Reset Onboarding shape: clear all three
          // tour markers so welcome + editor + column-chevron all reappear.
          try {
            localStorage.removeItem("dig.tour.home");
            localStorage.removeItem("dig.tour.editor.v1");
            localStorage.removeItem("dig.tour.column_chevron");
          } catch { /* ignore */ }
          router.push("/");
          toast("Tour will reopen on the home page");
        },
      },
      {
        id: "act:invalidate", group: "Actions",
        label: "Refresh all data",
        emoji: "🔄",
        run: () => {
          queryClient.invalidateQueries();
          toast.success("Refetching…");
        },
      },
      {
        id: "act:mode-cycle",
        group: "Mode",
        label: `Cycle expertise mode (current: ${EXPERTISE_LABEL[expertise.level]})`,
        emoji: "🌱",
        hint: "⌘⇧E",
        run: () => {
          const order: ExpertiseLevel[] = ["beginner", "builder", "engineer"];
          const next = order[(order.indexOf(expertise.level) + 1) % order.length];
          expertise.setLevel(next);
          toast.success(`Mode: ${EXPERTISE_LABEL[next]}`);
        },
      },
      ...(["beginner", "builder", "engineer"] as ExpertiseLevel[]).map((id) => ({
        id: `act:mode-${id}`,
        group: "Mode",
        label: `Switch to ${EXPERTISE_LABEL[id]}`,
        emoji: id === "beginner" ? "🌱" : id === "builder" ? "🪴" : "🌳",
        run: () => {
          expertise.setLevel(id);
          toast.success(`Mode: ${EXPERTISE_LABEL[id]}`);
        },
      })),
    );
    for (const d of datasets.data ?? []) {
      out.push({
        id: `ds:${d.id}`,
        group: "Datasets",
        label: d.name,
        emoji: "📊",
        hint: `${fmtInt(d.rowCount)} rows · ${d.connector}`,
        run: () => router.push(`/datasets/${d.id}`),
      });
    }
    // Recent items group — shown at the TOP of the palette when the
    // query is empty (CMDK natively sorts by command order). Round-5
    // W5 finding: cmdk reset alphabetically every open, so frequent
    // pipelines were never at the user's fingertips.
    //
    // Round-5 follow-up: prune entries whose live record no longer
    // exists. After a reseed or manual delete, the localStorage cache
    // would otherwise serve stale ULIDs and clicks would land on the
    // 404 "pipeline not found" screen.
    const livePipelineIds = new Set((pipelines.data ?? []).map((p) => p.id));
    const liveDatasetIds = new Set((datasets.data ?? []).map((d) => d.id));
    const recentPipelines = getRecent("pipeline").filter(
      (r) => !pipelines.data || livePipelineIds.has(r.id),
    );
    const recentSet = new Set(recentPipelines.map((r) => r.id));
    for (const r of recentPipelines) {
      out.push({
        id: `recent:pipe:${r.id}`,
        group: "Recent",
        label: r.label || r.id,
        emoji: "🕒",
        hint: "pipeline",
        run: () => router.push(`/pipelines/${r.id}`),
      });
    }
    const recentDatasets = getRecent("dataset").filter(
      (r) => !datasets.data || liveDatasetIds.has(r.id),
    );
    for (const r of recentDatasets) {
      out.push({
        id: `recent:ds:${r.id}`,
        group: "Recent",
        label: r.label || r.id,
        emoji: "🕒",
        hint: "dataset",
        run: () => router.push(`/datasets/${r.id}`),
      });
    }
    const favPipelines = new Set(listFavorites("pipeline"));
    for (const p of pipelines.data ?? []) {
      const star = favPipelines.has(p.id) ? "⭐ " : "";
      out.push({
        id: `pipe:${p.id}`,
        group: "Pipelines",
        label: `${star}${p.name}`,
        emoji: "🛤",
        hint: `${p.nodeCount} step${p.nodeCount === 1 ? "" : "s"}`,
        run: () => router.push(`/pipelines/${p.id}`),
      });
      // Round-5 W5: per-pipeline action verbs. Recent items above keep
      // navigation fast; these handle "do something to a pipeline I
      // can name" without opening the canvas first.
      out.push({
        id: `pipe:run:${p.id}`,
        group: "Pipeline actions",
        label: `▶ Run ${p.name}`,
        emoji: "▶️",
        searchHints: p.id,
        run: async () => {
          try {
            const run = await api.startRun(p.id);
            toast.success(`Run started for ${p.name}`, {
              action: {
                label: "Open",
                onClick: () => router.push(`/runs/${run.id}`),
              },
            });
          } catch (e) {
            toast.error(`Run failed: ${(e as Error).message}`);
          }
        },
      });
      out.push({
        id: `pipe:dup:${p.id}`,
        group: "Pipeline actions",
        label: `📑 Duplicate ${p.name}`,
        emoji: "📑",
        searchHints: p.id,
        run: async () => {
          try {
            const doc = await api.clonePipeline(p.id, `${p.name} (copy)`);
            router.push(`/pipelines/${doc.id}`);
          } catch (e) {
            toast.error(`Could not duplicate: ${(e as Error).message}`);
          }
        },
      });
      out.push({
        id: `pipe:schedule:${p.id}`,
        group: "Pipeline actions",
        label: `⏰ Schedule ${p.name}`,
        emoji: "⏰",
        searchHints: p.id,
        run: () => router.push(`/schedules?pipeline=${p.id}`),
      });
      out.push({
        id: `pipe:link:${p.id}`,
        group: "Pipeline actions",
        label: `🔗 Copy link to ${p.name}`,
        emoji: "🔗",
        searchHints: p.id,
        run: () => {
          try {
            const url = `${window.location.origin}/pipelines/${p.id}`;
            navigator.clipboard.writeText(url);
            toast.success("Link copied");
          } catch {
            toast.error("Clipboard unavailable");
          }
        },
      });
      out.push({
        id: `pipe:export:${p.id}`,
        group: "Pipeline actions",
        label: `⬇ Export ${p.name} as JSON`,
        emoji: "⬇",
        searchHints: `${p.id} download dpack`,
        run: async () => {
          // Round 8 security: previously we did
          // ``window.open(`/api/pipelines/${id}/export.json?token=…`)``
          // which exposes the bearer token in the Referer header on the
          // next navigation + in browser history. Switch to fetch +
          // blob-download so the token only ever rides in the
          // ``Authorization`` header (handled by the api client).
          try {
            const blob = await api.exportPipeline(p.id);
            const json = JSON.stringify(blob, null, 2);
            const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
            const a = document.createElement("a");
            a.href = url;
            a.download = `${p.name}.dig.json`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
          } catch (e) {
            toast.error(`Export failed: ${(e as Error).message}`, { duration: 8000 });
          }
        },
      });
    }
    // Suppress duplicate "Pipelines" entries when a recent already
    // surfaced them at the top.
    void recentSet;
    for (const s of stepsQ.data ?? []) {
      // The `aliases` array is search-only — surfacing it through the
      // cmdk value prop makes typing "merge" find `join`, "predict"
      // find `forecast`, etc. without changing the visible UI. Tags
      // come along for free.
      out.push({
        id: `step:${s.id}`,
        group: "Steps reference",
        label: s.label,
        emoji: undefined,
        hint: s.description?.slice(0, 80),
        searchHints: [
          ...(s.aliases ?? []),
          ...(s.tags ?? []),
          s.id,
        ].join(" "),
        run: () => {
          // Round-5 W1 finding: previously the palette only toasted a
          // hint and did nothing. When the user is already in a
          // pipeline editor, dispatch a custom event that the page
          // listens for and adds the step at the focused position.
          if (window.location.pathname.startsWith("/pipelines/")) {
            const ev = new CustomEvent("dig:cmdk:add-step", { detail: { stepId: s.id } });
            window.dispatchEvent(ev);
            toast.success(`Added ${s.label}`);
          } else {
            toast(`${s.label} (${s.id}) — open a pipeline editor and add it from the strip.`);
          }
        },
      });
    }
    // Workspace search hits. We skip pipeline /
    // dataset hits (the local cmdk filter already covers them via the
    // separate Datasets / Pipelines groups) and surface only the
    // novel signal: column matches + tag matches.
    for (const hit of wsSearch.data?.hits ?? []) {
      if (hit.kind === "column") {
        out.push({
          id: `ws:col:${hit.id}`,
          group: "Columns",
          label: hit.label,
          emoji: "🅰",
          hint: hit.subtitle ?? undefined,
          run: () => router.push(hit.href),
        });
      } else if (hit.kind === "tag" || hit.tag_match) {
        out.push({
          id: `ws:tag:${hit.id}`,
          group: "Tags",
          label: hit.tag_match ? `#${hit.tag_match}` : hit.label,
          emoji: "🏷",
          hint: `${hit.kind} · ${hit.label}`,
          run: () => router.push(hit.href),
        });
      }
    }
    return out;
  }, [
    datasets.data, pipelines.data, stepsQ.data, wsSearch.data,
    settings.theme, settings.livePreview, settings.sampleRows,
    expertise, router, queryClient,
  ]);

  const grouped = useMemo(() => {
    const out: Record<string, Action[]> = {};
    for (const a of actions) (out[a.group] ||= []).push(a);
    return out;
  }, [actions]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60]"
        >
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.97 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.97 }}
            transition={reduce ? { duration: 0.12 } : { type: "spring", stiffness: 320, damping: 28 }}
            className="absolute left-1/2 top-[18vh] -translate-x-1/2 w-[min(620px,92vw)] rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl overflow-hidden"
          >
            <Command className="flex flex-col" shouldFilter>
              <Command.Input
                value={query}
                onValueChange={setQuery}
                autoFocus
                placeholder="Search anything — datasets, pipelines, actions, steps…"
                className="w-full px-4 py-3 text-sm bg-transparent outline-none border-b border-border"
              />
              <Command.List className="max-h-[420px] overflow-y-auto p-2">
                <Command.Empty className="px-4 py-8 text-center text-xs text-muted-foreground">
                  No matches.
                </Command.Empty>
                {Object.entries(grouped).map(([group, items]) => (
                  <Command.Group
                    key={group}
                    heading={group}
                    className="text-[10px] uppercase tracking-widest text-muted-foreground/70 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
                  >
                    {items.map((a) => (
                      <Command.Item
                        key={a.id}
                        // Round-9 fix: previously folded `a.group` into
                        // the searchable value so typing "Actions"
                        // matched every Action regardless of label.
                        // Group is already a separate cmdk axis.
                        // We also append `a.id` so two items with the
                        // same label (e.g. two "Untitled pipeline"
                        // entries) don't dedupe to one selectable row.
                        value={`${a.label} ${a.hint ?? ""} ${a.searchHints ?? ""} ${a.id}`}
                        onSelect={() => {
                          a.run();
                          setOpen(false);
                          setQuery("");
                        }}
                        className="px-2 py-1.5 rounded text-sm flex items-center gap-2 cursor-pointer data-[selected=true]:bg-muted"
                      >
                        {a.emoji && <span aria-hidden className="text-base">{a.emoji}</span>}
                        <span className="flex-1 truncate">{a.label}</span>
                        {a.hint && (
                          <span className="text-[10px] text-muted-foreground truncate max-w-[200px]">
                            {a.hint}
                          </span>
                        )}
                      </Command.Item>
                    ))}
                  </Command.Group>
                ))}
              </Command.List>
              <footer className="px-4 py-2 border-t border-border text-[10px] text-muted-foreground flex items-center gap-3 flex-wrap">
                <span><kbd className="font-mono">↑↓</kbd> navigate</span>
                <span><kbd className="font-mono">↵</kbd> select</span>
                <span><kbd className="font-mono">⇥</kbd> cycle focus</span>
                <span><kbd className="font-mono">esc</kbd> close</span>
                <span className="flex-1" />
                <button
                  type="button"
                  onClick={() => {
                    const order: ExpertiseLevel[] = ["beginner", "builder", "engineer"];
                    const next = order[(order.indexOf(expertise.level) + 1) % order.length];
                    expertise.setLevel(next);
                    toast.success(`Mode: ${EXPERTISE_LABEL[next]}`);
                  }}
                  title="Cycle expertise mode (⌘⇧E)"
                  className="px-1.5 py-0.5 rounded border border-border hover:border-foreground/30 transition-colors inline-flex items-center gap-1"
                >
                  <kbd className="font-mono opacity-70">⌘⇧E</kbd>
                  {EXPERTISE_LABEL[expertise.level]}
                </button>
                <span><kbd className="font-mono">⌘K</kbd> toggle</span>
              </footer>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

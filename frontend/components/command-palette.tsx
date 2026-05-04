"use client";

import { useEffect, useMemo, useState } from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import {
  setSettings,
  useSettings,
  useExpertise,
  EXPERTISE_LABEL,
  type ExpertiseLevel,
} from "@/lib/settings";
import { fmtInt } from "@/lib/format-number";

interface Action {
  id: string;
  label: string;
  emoji?: string;
  hint?: string;
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
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();
  const settings = useSettings();
  const expertise = useExpertise();
  const queryClient = useQueryClient();

  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.listDatasets, enabled: open });
  const pipelines = useQuery({ queryKey: ["pipelines"], queryFn: api.listPipelines, enabled: open });
  const stepsQ = useQuery({ queryKey: ["steps"], queryFn: api.listSteps, enabled: open, staleTime: 60_000 });

  // Open / close keybindings + ⌘⇧E mode cycle
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
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
        id: "go:settings", group: "Go to", label: "Settings", emoji: "⚙️",
        run: () => router.push("/settings"),
      },
      {
        id: "act:theme", group: "Actions",
        label: `Theme: ${settings.theme} → next`,
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
          try { localStorage.removeItem("dig.tour.home"); } catch { /* ignore */ }
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
    for (const p of pipelines.data ?? []) {
      out.push({
        id: `pipe:${p.id}`,
        group: "Pipelines",
        label: p.name,
        emoji: "🛤",
        hint: `${p.nodeCount} step${p.nodeCount === 1 ? "" : "s"}`,
        run: () => router.push(`/pipelines/${p.id}`),
      });
    }
    for (const s of stepsQ.data ?? []) {
      out.push({
        id: `step:${s.id}`,
        group: "Steps reference",
        label: s.label,
        emoji: undefined,
        hint: s.description?.slice(0, 80),
        run: () => {
          toast(`${s.label} (${s.id}) — open a pipeline editor and add it from the strip.`);
        },
      });
    }
    return out;
  }, [datasets.data, pipelines.data, stepsQ.data, settings.theme, settings.livePreview, settings.sampleRows, expertise, router, queryClient]);

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
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
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
                        value={`${a.group} ${a.label} ${a.hint ?? ""}`}
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
              <footer className="px-4 py-2 border-t border-border text-[10px] text-muted-foreground flex items-center gap-3">
                <span><kbd className="font-mono">↑↓</kbd> navigate</span>
                <span><kbd className="font-mono">↵</kbd> select</span>
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
                  className="px-1.5 py-0.5 rounded border border-border hover:border-foreground/30 transition-colors"
                >
                  {EXPERTISE_LABEL[expertise.level]}
                </button>
                <span>⌘K to toggle</span>
              </footer>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

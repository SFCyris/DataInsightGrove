"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";

interface Shortcut { keys: string; desc: string }
const GROUPS: Array<{ name: string; emoji: string; items: Shortcut[] }> = [
  {
    name: "Global", emoji: "🌐",
    items: [
      { keys: "⌘K / Ctrl+K", desc: "Open command palette" },
      { keys: "?",            desc: "Show this cheatsheet" },
      { keys: "Esc",          desc: "Close any overlay" },
    ],
  },
  {
    name: "Editor", emoji: "🛤",
    items: [
      { keys: "⌘Z",            desc: "Undo last edit" },
      { keys: "⌘⇧Z",          desc: "Redo" },
      { keys: "⌫ / Delete",    desc: "Delete selected step / dataset" },
    ],
  },
  {
    name: "Live grid", emoji: "📊",
    items: [
      { keys: "Click column name", desc: "Open column profile drawer" },
      { keys: "Click ⋯ on header", desc: "Open column menu (filter / sort / cast / drop / group / derive)" },
      { keys: "Right-click header", desc: "Same as ⋯" },
      { keys: "⌘+click cell",      desc: "Filter to this value" },
      { keys: "⌘+Alt+click cell",  desc: "Exclude this value" },
    ],
  },
  {
    name: "Pipeline strip", emoji: "🪡",
    items: [
      { keys: "Click pill",  desc: "Focus the grid on that step's output" },
      { keys: "✕ on pill",   desc: "Remove the step" },
      { keys: "+ Add step",  desc: "Open the searchable step picker" },
    ],
  },
];

export function ShortcutsCheatsheet() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isInput = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (isInput) return;
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60]"
        >
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
            className="absolute left-1/2 top-[14vh] -translate-x-1/2 w-[min(640px,92vw)] rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl overflow-hidden"
          >
            <header className="px-4 py-3 border-b border-border flex items-center gap-2">
              <span className="text-2xl">⌨️</span>
              <div className="flex-1">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Keyboard</p>
                <h2 className="font-semibold">Shortcuts</h2>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                ✕
              </button>
            </header>
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4 max-h-[60vh] overflow-y-auto">
              {GROUPS.map((g) => (
                <section key={g.name}>
                  <h3 className="text-xs font-medium mb-2 flex items-center gap-1.5">
                    <span aria-hidden>{g.emoji}</span>
                    {g.name}
                  </h3>
                  <ul className="space-y-1.5">
                    {g.items.map((s) => (
                      <li key={s.keys} className="text-xs flex items-start gap-2">
                        <kbd className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-muted border border-border whitespace-nowrap shrink-0">
                          {s.keys}
                        </kbd>
                        <span className="text-muted-foreground leading-snug">{s.desc}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
            <footer className="px-4 py-2 border-t border-border text-[10px] text-muted-foreground">
              Press <kbd className="font-mono">?</kbd> anywhere to reopen.
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

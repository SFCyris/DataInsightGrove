"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type FsBrowseResult } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

/**
 * Server-side directory picker.
 *
 * Browsers can't expose the OS file picker for security reasons (the picker
 * would either return paths the backend can't use or refuse to show real
 * filesystem paths at all). So we ship our own: the modal calls
 * /fs/browse?path=... and lets the user navigate one level at a time.
 *
 * Opens at `initialPath` — typically the current value of the field. If the
 * field is empty we fall back to the user's home directory (the backend
 * handles the empty-path → $HOME default). Breadcrumbs across the top let
 * the user jump up multiple levels in one click.
 */

interface Props {
  open: boolean;
  initialPath: string;
  onClose: () => void;
  onSelect: (path: string) => void;
  /** What the user is picking — used in headings and the confirm button.
   *  e.g. "input directory", "output directory". */
  forLabel?: string;
}

export function DirectoryPickerModal({ open, initialPath, onClose, onSelect, forLabel }: Props) {
  const reduce = useReducedMotion();
  // The path currently displayed by the picker. Starts at `initialPath` each
  // time the modal opens so the user lands on the value they're editing.
  const [path, setPath] = useState<string>(initialPath);
  // Free-text path input — separate from `path` so typing doesn't trigger a
  // request per keystroke. The user commits with Enter or by clicking "Go".
  const [draftPath, setDraftPath] = useState<string>(initialPath);

  // Re-anchor when the modal opens / the initial path changes.
  useEffect(() => {
    if (open) {
      setPath(initialPath);
      setDraftPath(initialPath);
    }
  }, [open, initialPath]);

  // Escape closes; outside-click closes (handled by the backdrop).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const q = useQuery({
    queryKey: ["fs-browse", path],
    queryFn: () => api.browseDir(path || undefined),
    enabled: open,
    // The same path doesn't change frequently — short stale window keeps
    // navigation snappy without flooding the server.
    staleTime: 5_000,
  });

  // Focus the path input on first open so users can paste without an extra
  // click. ref is stable; effect only fires on `open` transitions.
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (open) {
      // Defer focus so the modal's mount animation doesn't fight us.
      const t = setTimeout(() => inputRef.current?.select(), 60);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Resolved (post-server) path is what actually gets returned on confirm —
  // the server normalizes ~/ etc. and resolves symlinks. Falls back to the
  // requested path while the request is in flight.
  const displayedPath = q.data?.path ?? path;
  const exists = q.data?.exists ?? true;
  const entries = q.data?.entries ?? [];
  const parent = q.data?.parent ?? null;
  const home = q.data?.home ?? "";

  const breadcrumbs = useMemo(() => buildBreadcrumbs(displayedPath), [displayedPath]);

  const goTo = (next: string) => {
    setPath(next);
    setDraftPath(next);
  };
  const commitDraft = () => {
    if (draftPath.trim() && draftPath !== path) goTo(draftPath.trim());
  };

  if (!open) return null;

  const initial = reduce ? false : { opacity: 0, y: 8, scale: 0.98 };
  const animate = { opacity: 1, y: 0, scale: 1 };
  const exit = reduce ? undefined : { opacity: 0, y: 4, scale: 0.98 };
  const transition = reduce
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 320, damping: 28 };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[80] flex items-center justify-center p-4" role="dialog" aria-modal="true">
        {/* Backdrop */}
        <motion.div
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduce ? undefined : { opacity: 0 }}
          className="absolute inset-0 bg-foreground/40 backdrop-blur-sm"
          onClick={onClose}
        />
        {/* Card */}
        <motion.div
          initial={initial}
          animate={animate}
          exit={exit}
          transition={transition}
          className="relative w-full max-w-xl bg-card text-card-foreground rounded-xl shadow-2xl border border-border flex flex-col max-h-[80vh]"
        >
          {/* Header */}
          <header className="px-5 py-4 border-b border-border flex items-center gap-3">
            <span aria-hidden className="text-2xl">📁</span>
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold tracking-tight">
                Pick {forLabel ? `the ${forLabel}` : "a directory"}
              </h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Navigate the server's filesystem — paths are resolved on the backend, not the browser.
              </p>
            </div>
          </header>

          {/* Path input + Go */}
          <div className="px-5 pt-3 flex items-center gap-2">
            <input
              ref={inputRef}
              value={draftPath}
              onChange={(e) => setDraftPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitDraft();
                }
              }}
              placeholder="/Users/me/data"
              className="flex-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm font-mono"
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
            />
            <Button size="sm" variant="outline" onClick={commitDraft}>Go</Button>
          </div>

          {/* Breadcrumbs */}
          <div className="px-5 pt-2 flex flex-wrap items-center gap-1 text-xs">
            {breadcrumbs.map((c, i) => (
              <span key={c.path} className="flex items-center gap-1">
                {i > 0 && <span aria-hidden className="text-muted-foreground/50">/</span>}
                <button
                  type="button"
                  onClick={() => goTo(c.path)}
                  className="px-1.5 py-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                >
                  {c.label}
                </button>
              </span>
            ))}
          </div>

          {/* Quick shortcuts */}
          <div className="px-5 pt-2 flex flex-wrap gap-1.5 text-xs">
            {home && (
              <button type="button" onClick={() => goTo(home)}
                className="px-2 py-0.5 rounded-full border border-border hover:border-foreground/30 transition-colors">
                🏠 Home
              </button>
            )}
            <button type="button" onClick={() => goTo("/")}
              className="px-2 py-0.5 rounded-full border border-border hover:border-foreground/30 transition-colors">
              📁 /
            </button>
            {parent && (
              <button type="button" onClick={() => goTo(parent)}
                className="px-2 py-0.5 rounded-full border border-border hover:border-foreground/30 transition-colors">
                ↑ Parent
              </button>
            )}
          </div>

          {/* Listing */}
          <div className="flex-1 min-h-[160px] mt-3 mx-5 mb-3 rounded-lg border border-border overflow-y-auto">
            {q.isLoading && (
              <p className="px-3 py-3 text-xs text-muted-foreground italic">Loading…</p>
            )}
            {q.isError && (
              <p className="px-3 py-3 text-xs text-destructive">
                Couldn&apos;t list directory ({(q.error as Error).message}).
              </p>
            )}
            {q.data && !exists && (
              <p className="px-3 py-3 text-xs text-rose-600 dark:text-rose-400">
                ⚠ This path doesn&apos;t exist. Use the breadcrumbs or 🏠 Home to navigate elsewhere.
              </p>
            )}
            {q.data && exists && entries.length === 0 && (
              <p className="px-3 py-3 text-xs text-muted-foreground italic">
                (no subdirectories)
              </p>
            )}
            <ul className="divide-y divide-border/40">
              {entries.map((entry) => {
                const childPath = joinPath(displayedPath, entry.name);
                return (
                  <li key={entry.name}>
                    <button
                      type="button"
                      onDoubleClick={() => goTo(childPath)}
                      onClick={() => goTo(childPath)}
                      className="w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 hover:bg-muted/50 transition-colors"
                      title={`Open ${childPath}`}
                    >
                      <span aria-hidden>📁</span>
                      <span className="truncate">{entry.name}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Footer */}
          <footer className="px-5 py-3 border-t border-border flex items-center justify-between gap-3">
            <p className="text-[11px] text-muted-foreground truncate flex-1" title={displayedPath}>
              📌 <span className="font-mono">{displayedPath}</span>
            </p>
            <div className="flex gap-2 shrink-0">
              <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
              <Button
                size="sm"
                disabled={!exists}
                onClick={() => {
                  onSelect(displayedPath);
                  onClose();
                }}
              >
                ✅ Use this folder
              </Button>
            </div>
          </footer>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}

function joinPath(base: string, name: string): string {
  if (base.endsWith("/")) return base + name;
  return base + "/" + name;
}

function buildBreadcrumbs(absPath: string): { label: string; path: string }[] {
  // Split a posix path into clickable segments. macOS / Linux paths only —
  // DIG is a self-hosted tool and the backend already returns posix-style
  // resolved paths (Path.resolve on Windows would be different; out of scope).
  const parts = absPath.split("/").filter(Boolean);
  const out: { label: string; path: string }[] = [{ label: "/", path: "/" }];
  let acc = "";
  for (const p of parts) {
    acc += "/" + p;
    out.push({ label: p, path: acc });
  }
  return out;
}

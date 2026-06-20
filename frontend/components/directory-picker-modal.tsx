"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type FsBrowseResult } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

/**
 * Server-side path picker — directories OR files.
 *
 * Browsers can't expose the OS file picker for security reasons (it would
 * either return paths the backend can't use or refuse to show real
 * filesystem paths). So we ship our own: the modal calls /fs/browse and
 * lets the user navigate one level at a time.
 *
 * `mode`:
 *   - "directory" (default): lists directories; confirm returns the
 *     currently-shown directory ("Use this folder"). Back-compat for the
 *     input/output/log-dir pickers.
 *   - "file": also lists files (optionally filtered by `extensions`);
 *     the user clicks a file to select it; confirm returns that file
 *     ("Use this file").
 *
 * Opens at `initialPath`. If that's a file path (file mode), the backend
 * lists its parent directory and we pre-highlight the file. Empty →
 * the backend falls back to $HOME.
 */

interface Props {
  open: boolean;
  initialPath: string;
  onClose: () => void;
  onSelect: (path: string) => void;
  /** What the user is picking — used in headings + the confirm button.
   *  e.g. "input directory", "JDBC driver JAR". */
  forLabel?: string;
  mode?: "directory" | "file";
  /** File-mode extension allow-list, e.g. [".jar"]. Leading dot optional. */
  extensions?: string[];
}

function _basename(p: string): string {
  const t = p.replace(/[/\\]+$/, "");
  return t.split(/[/\\]/).pop() ?? "";
}
function _hasFileShape(p: string): boolean {
  // Heuristic: a trailing path segment with a dot-extension looks like a file.
  const base = _basename(p);
  return base.includes(".") && !p.endsWith("/");
}

export function DirectoryPickerModal({
  open, initialPath, onClose, onSelect, forLabel, mode = "directory", extensions,
}: Props) {
  const reduce = useReducedMotion();
  const isFileMode = mode === "file";

  // The directory currently displayed by the picker.
  const [path, setPath] = useState<string>(initialPath);
  // Free-text path input — separate from `path` so typing doesn't fire a
  // request per keystroke. Committed with Enter / "Go".
  const [draftPath, setDraftPath] = useState<string>(initialPath);
  // File mode: the file the user has clicked (full path), or "" if none.
  const [selectedFile, setSelectedFile] = useState<string>(
    isFileMode && _hasFileShape(initialPath) ? initialPath : "",
  );

  // Re-anchor when the modal opens / the initial path changes.
  useEffect(() => {
    if (open) {
      setPath(initialPath);
      setDraftPath(initialPath);
      setSelectedFile(isFileMode && _hasFileShape(initialPath) ? initialPath : "");
    }
  }, [open, initialPath, isFileMode]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const q = useQuery({
    queryKey: ["fs-browse", path, isFileMode, (extensions ?? []).join(",")],
    queryFn: () => api.browseDir(path || undefined, isFileMode ? { files: true, exts: extensions } : undefined),
    enabled: open,
    staleTime: 5_000,
  });

  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.select(), 60);
      return () => clearTimeout(t);
    }
  }, [open]);

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
    const v = draftPath.trim();
    if (!v || v === path) return;
    // In file mode, if the user typed a full file path, select it + browse
    // its parent. Otherwise treat it as a directory to navigate into.
    if (isFileMode && _hasFileShape(v)) setSelectedFile(v);
    goTo(v);
  };

  if (!open) return null;

  const initial = reduce ? false : { opacity: 0, y: 8, scale: 0.98 };
  const animate = { opacity: 1, y: 0, scale: 1 };
  const exit = reduce ? undefined : { opacity: 0, y: 4, scale: 0.98 };
  const transition = reduce
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 320, damping: 28 };

  const confirmDisabled = isFileMode ? !selectedFile : !exists;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[80] flex items-center justify-center p-4" role="dialog" aria-modal="true">
        <motion.div
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduce ? undefined : { opacity: 0 }}
          className="absolute inset-0 bg-foreground/40 backdrop-blur-sm"
          onClick={onClose}
        />
        <motion.div
          initial={initial}
          animate={animate}
          exit={exit}
          transition={transition}
          className="relative w-full max-w-xl bg-card text-card-foreground rounded-xl shadow-2xl border border-border flex flex-col max-h-[80vh]"
        >
          <header className="px-5 py-4 border-b border-border flex items-center gap-3">
            <span aria-hidden className="text-2xl">{isFileMode ? "📄" : "📁"}</span>
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold tracking-tight">
                Pick {forLabel ? `the ${forLabel}` : isFileMode ? "a file" : "a directory"}
              </h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Navigate the server's filesystem — paths are resolved on the backend, not the browser.
                {isFileMode && extensions?.length ? ` Showing ${extensions.join(" / ")} files.` : ""}
              </p>
            </div>
          </header>

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
              placeholder={isFileMode ? "/Users/me/drivers/driver.jar" : "/Users/me/data"}
              className="flex-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm font-mono"
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
            />
            <Button size="sm" variant="outline" onClick={commitDraft}>Go</Button>
          </div>

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
                {isFileMode
                  ? (extensions?.length ? `(no ${extensions.join(" / ")} files or subfolders here)` : "(empty folder)")
                  : "(no subdirectories)"}
              </p>
            )}
            <ul className="divide-y divide-border/40">
              {entries.map((entry) => {
                const childPath = joinPath(displayedPath, entry.name);
                const isSelected = isFileMode && !entry.is_dir && childPath === selectedFile;
                return (
                  <li key={entry.name}>
                    <button
                      type="button"
                      onDoubleClick={() => {
                        if (entry.is_dir) goTo(childPath);
                        else { setSelectedFile(childPath); onSelect(childPath); onClose(); }
                      }}
                      onClick={() => {
                        if (entry.is_dir) goTo(childPath);
                        else setSelectedFile(childPath); // file mode only — dirs nav, files select
                      }}
                      className={[
                        "w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 transition-colors",
                        isSelected ? "bg-emerald-500/10 ring-1 ring-inset ring-emerald-500/40" : "hover:bg-muted/50",
                      ].join(" ")}
                      title={entry.is_dir ? `Open ${childPath}` : `Select ${childPath}`}
                    >
                      <span aria-hidden>{entry.is_dir ? "📁" : "📄"}</span>
                      <span className="truncate">{entry.name}</span>
                      {isSelected && <span className="ml-auto text-emerald-600 dark:text-emerald-400">✓</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <footer className="px-5 py-3 border-t border-border flex items-center justify-between gap-3">
            <p className="text-[11px] text-muted-foreground truncate flex-1" title={isFileMode ? (selectedFile || displayedPath) : displayedPath}>
              📌 <span className="font-mono">{isFileMode ? (selectedFile || "(no file selected)") : displayedPath}</span>
            </p>
            <div className="flex gap-2 shrink-0">
              <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
              <Button
                size="sm"
                disabled={confirmDisabled}
                onClick={() => {
                  onSelect(isFileMode ? selectedFile : displayedPath);
                  onClose();
                }}
              >
                {isFileMode ? "✅ Use this file" : "✅ Use this folder"}
              </Button>
            </div>
          </footer>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}

/** Convenience wrapper: a file picker (DirectoryPickerModal in file mode). */
export function FilePickerModal(props: Omit<Props, "mode">) {
  return <DirectoryPickerModal {...props} mode="file" />;
}

function joinPath(base: string, name: string): string {
  if (base.endsWith("/")) return base + name;
  return base + "/" + name;
}

function buildBreadcrumbs(absPath: string): { label: string; path: string }[] {
  const parts = absPath.split("/").filter(Boolean);
  const out: { label: string; path: string }[] = [{ label: "/", path: "/" }];
  let acc = "";
  for (const p of parts) {
    acc += "/" + p;
    out.push({ label: p, path: acc });
  }
  return out;
}

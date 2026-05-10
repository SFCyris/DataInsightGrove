"use client";

import { useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError, type InstalledPack, type StagedPack } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

/**
 * Settings → Step Packs.
 *
 * Two surfaces in one panel:
 *   1. ➕ Install — drag-drop / browse for a `.dpack`. On accept, the
 *      backend stages the archive and returns its manifest, which we
 *      render in a review modal so the operator can see exactly what
 *      will be installed before pressing Confirm.
 *   2. 📦 Installed — a list of every registered pack with toggle /
 *      uninstall actions. The toggle hot-reloads the StepRegistry, so
 *      a disabled pack's steps disappear from the picker immediately.
 */
export function PacksSection() {
  const qc = useQueryClient();
  const installedQ = useQuery({
    queryKey: ["packs"],
    queryFn: api.listPacks,
    refetchOnWindowFocus: false,
  });

  const [staged, setStaged] = useState<StagedPack | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const upload = async (f: File) => {
    setBusy(true);
    try {
      const out = await api.uploadPack(f);
      setStaged(out);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      toast.error(`Upload failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  };

  const confirmInstall = async () => {
    if (!staged) return;
    setBusy(true);
    try {
      const out = await api.installPack(staged.pack_id, staged.version);
      // Surface dep-install outcome explicitly — auto-install runs pip
      // and the operator should see what happened.
      if (out.dep_install) {
        if (out.dep_install.success) {
          if (out.dep_install.requirements.length > 0) {
            toast.success(
              `Installed ${staged.label} v${staged.version} ` +
              `+ ${out.dep_install.requirements.length} dep(s) ` +
              `in ${out.dep_install.elapsed_sec.toFixed(1)}s`,
            );
          } else {
            toast.success(`Installed ${staged.label} v${staged.version}`);
          }
        } else if (out.dep_install.skipped_reason) {
          toast.warning(
            `Installed ${staged.label}, but Python deps were not installed: ` +
            out.dep_install.skipped_reason,
          );
        } else {
          toast.error(
            `Installed ${staged.label}, but pip failed for: ` +
            out.dep_install.requirements.join(", ") + ". See backend logs.",
          );
        }
      } else {
        toast.success(`Installed ${staged.label} v${staged.version}`);
      }
      setStaged(null);
      qc.invalidateQueries({ queryKey: ["packs"] });
      qc.invalidateQueries({ queryKey: ["steps"] });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      toast.error(`Install failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  };

  const cancelStaged = async () => {
    if (!staged) return;
    try {
      await api.discardPendingPack(staged.pack_id, staged.version);
    } catch {
      /* discard is best-effort; tell the user only when the user-driven
         install/uninstall fails — silent discard is fine. */
    }
    setStaged(null);
  };

  const onToggle = async (id: string, enabled: boolean) => {
    try {
      await api.togglePack(id, enabled);
      toast.success(`${id} ${enabled ? "enabled" : "disabled"}`);
      qc.invalidateQueries({ queryKey: ["packs"] });
      qc.invalidateQueries({ queryKey: ["steps"] });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      toast.error(`Toggle failed: ${msg}`);
    }
  };

  const onUninstall = async (p: InstalledPack) => {
    if (!confirm(
      `Uninstall ${p.label} v${p.version}?\n\nThis removes ${p.steps.length} step(s) ` +
      `from your DIG instance. Pipelines that reference these steps will fail to load.`,
    )) return;
    try {
      await api.uninstallPack(p.id);
      toast.success(`Uninstalled ${p.label}`);
      qc.invalidateQueries({ queryKey: ["packs"] });
      qc.invalidateQueries({ queryKey: ["steps"] });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      toast.error(`Uninstall failed: ${msg}`);
    }
  };

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const f = files[0];
    if (!f.name.toLowerCase().endsWith(".dpack") && !f.name.toLowerCase().endsWith(".zip")) {
      toast.error("Pack archives must end in .dpack or .zip");
      return;
    }
    upload(f);
  };

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight flex items-center gap-2">
          📦 Step Packs
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Step packs are distributable bundles of step plugins. Drop a{" "}
          <code className="font-mono text-xs">.dpack</code> archive here to
          install one. Steps from enabled packs appear alongside built-in
          steps in the pipeline picker.
        </p>
      </header>

      {/* Upload zone */}
      <section
        onDragEnter={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={`rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          dragOver
            ? "border-violet-400 bg-violet-50 dark:bg-violet-950/20"
            : "border-border bg-muted/20"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".dpack,.zip"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <p className="text-sm">
          {busy ? (
            <span className="flex items-center justify-center gap-2">
              <span className="inline-block animate-pulse">📦</span>
              <span>Reading pack…</span>
            </span>
          ) : (
            <>
              <span className="font-medium">Drop a .dpack file here</span>
              <span className="text-muted-foreground"> or </span>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="text-violet-700 dark:text-violet-300 hover:underline"
              >
                browse
              </button>
            </>
          )}
        </p>
        <p className="text-xs text-muted-foreground mt-2">
          Pack archives are zip files with a single root directory containing{" "}
          <code className="font-mono">pack.json</code>.
        </p>
      </section>

      {/* Installed list */}
      <section>
        <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
          📚 Installed packs
          <span className="text-xs text-muted-foreground">
            ({installedQ.data?.length ?? 0})
          </span>
        </h3>
        {installedQ.isLoading && (
          <p className="text-xs text-muted-foreground">Loading…</p>
        )}
        {installedQ.data && installedQ.data.length === 0 && (
          <p className="text-xs text-muted-foreground py-4">
            No packs installed yet. Drop a .dpack above to get started.
          </p>
        )}
        <ul className="space-y-2">
          {(installedQ.data ?? []).map((p) => (
            <motion.li
              key={p.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className={`rounded-lg border border-border p-3 ${
                p.enabled ? "bg-card" : "bg-muted/30 opacity-70"
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">{p.label}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                      v{p.version}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {p.steps.length} step{p.steps.length === 1 ? "" : "s"}
                    </span>
                    {p.license && (
                      <span className="text-[10px] text-muted-foreground">
                        · {p.license}
                      </span>
                    )}
                  </div>
                  {p.description && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {p.description}
                    </p>
                  )}
                  {p.python_requirements.length > 0 && (
                    <p className="text-[10px] text-amber-700 dark:text-amber-300 mt-1">
                      Python deps: {p.python_requirements.join(", ")}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => onToggle(p.id, !p.enabled)}
                    title={p.enabled ? "Disable (keeps files on disk)" : "Enable"}
                    className={`text-xs px-2 py-1 rounded transition-colors ${
                      p.enabled
                        ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300"
                        : "bg-muted text-muted-foreground hover:bg-muted/80"
                    }`}
                  >
                    {p.enabled ? "● enabled" : "○ disabled"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onUninstall(p)}
                    title="Uninstall — removes files + registry entry"
                    className="text-xs px-2 py-1 rounded text-rose-700 hover:bg-rose-100 dark:text-rose-300 dark:hover:bg-rose-950/40"
                  >
                    🗑 Uninstall
                  </button>
                </div>
              </div>
            </motion.li>
          ))}
        </ul>
      </section>

      {/* Review modal — staged but not yet installed */}
      <AnimatePresence>
        {staged && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={cancelStaged}
              className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ type: "spring", stiffness: 320, damping: 28 }}
              className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[640px] max-w-[92vw] max-h-[88vh] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden"
              role="dialog"
              aria-label="Review pack install"
            >
              <header className="px-5 py-4 border-b border-border flex items-center gap-3 shrink-0">
                <span className="text-2xl" aria-hidden>📦</span>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold truncate">{staged.label}</h3>
                  <p className="text-[11px] text-muted-foreground">
                    v{staged.version} · sha {staged.computed_checksum.slice(7, 19)}…
                    {staged.declared_checksum &&
                      staged.declared_checksum !== staged.computed_checksum && (
                        <span className="text-rose-600 ml-2">⚠ checksum mismatch</span>
                      )}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={cancelStaged}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Close"
                >
                  ✕
                </button>
              </header>
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 min-h-0">
                <p className="text-sm">{staged.description}</p>

                {staged.author || staged.license || staged.homepage ? (
                  <p className="text-xs text-muted-foreground flex items-center gap-3 flex-wrap">
                    {staged.author && <span>👤 {staged.author}</span>}
                    {staged.license && <span>📄 {staged.license}</span>}
                    {staged.homepage && (
                      <a
                        href={staged.homepage}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:underline text-violet-700 dark:text-violet-300"
                      >
                        🔗 homepage
                      </a>
                    )}
                  </p>
                ) : null}

                <div>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">
                    Steps that will be added ({staged.steps.length})
                  </p>
                  <ul className="space-y-1">
                    {staged.steps.map((sid) => {
                      const conflict = staged.conflicts.find((c) => c.step_id === sid);
                      return (
                        <li
                          key={sid}
                          className={`text-sm font-mono px-2 py-1 rounded ${
                            conflict
                              ? "bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-300"
                              : "bg-muted/40"
                          }`}
                        >
                          {conflict ? "⚠ " : "▸ "}
                          {sid}
                          {conflict && (
                            <span className="ml-2 text-[10px]">
                              conflicts with: {conflict.existing_source}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>

                {staged.python_requirements.length > 0 && (
                  <div className="rounded-md bg-violet-50 dark:bg-violet-950/30 border border-violet-200 dark:border-violet-800 p-3">
                    <p className="text-xs font-medium text-violet-900 dark:text-violet-200 mb-1">
                      📦 Python dependencies will be installed
                    </p>
                    <p className="text-[11px] text-violet-800 dark:text-violet-300 mb-2">
                      DIG runs pip into its own environment when you click
                      Install. To opt out (and install manually), set{" "}
                      <code className="font-mono">DIG_PACK_AUTO_INSTALL_DEPS=0</code>{" "}
                      before starting the backend.
                    </p>
                    <pre className="text-[11px] font-mono bg-background/70 rounded px-2 py-1 overflow-x-auto">
                      pip install {staged.python_requirements.join(" ")}
                    </pre>
                  </div>
                )}

                {staged.readme && (
                  <details className="rounded-md border border-border">
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium select-none">
                      📄 README
                    </summary>
                    <pre className="px-3 py-2 text-[11px] whitespace-pre-wrap font-sans text-muted-foreground max-h-64 overflow-y-auto">
                      {staged.readme}
                    </pre>
                  </details>
                )}
              </div>
              <footer className="px-5 py-3 border-t border-border flex items-center justify-end gap-2 shrink-0">
                <Button variant="ghost" size="sm" onClick={cancelStaged}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={confirmInstall}
                  disabled={busy || staged.conflicts.length > 0}
                >
                  {busy ? "Installing…" : staged.conflicts.length > 0
                    ? `${staged.conflicts.length} conflict(s) — resolve first`
                    : "✓ Install"}
                </Button>
              </footer>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError, type Dataset, type FsBrowseResult } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { toastError } from "@/lib/toast-error";

/**
 * "Reference an existing file as a dataset" modal.
 *
 * Companion to UploadDropzone — but where the dropzone *copies* a file into
 * DIG's managed area, this modal *references* a file that already lives
 * somewhere on the filesystem. The file is never copied, never moved,
 * never modified. DIG only records a pointer (the dataset's `source_uri`)
 * and materialises its own internal Parquet cache from the read.
 *
 * Pairs naturally with the input-data-is-sacred policy: the file the user
 * pointed us at stays untouched, even when the dataset reference is
 * deleted from the catalog. See docs/ADMINISTRATION.md §3.4.
 *
 * Connector is auto-detected from the file extension; an explicit
 * dropdown override is exposed for the unusual case (e.g. CSV with a
 * non-standard ".log" extension).
 */

interface Props {
  open: boolean;
  onClose: () => void;
  /** Called with the freshly-created Dataset record on success. */
  onCreated?: (d: Dataset) => void;
  /** Optional initial path the file browser opens at. */
  initialPath?: string;
}

const _CONNECTORS: { id: string; label: string; extensions: readonly string[] }[] = [
  { id: "csv",     label: "CSV / TSV / TXT",   extensions: ["csv", "tsv", "txt", "dat", "data", "tab", "psv"] },
  { id: "excel",   label: "Excel (.xlsx/.xls)", extensions: ["xlsx", "xls", "xlsm"] },
  { id: "parquet", label: "Parquet",            extensions: ["parquet", "pq"] },
  { id: "json",    label: "JSON / NDJSON",     extensions: ["json", "ndjson", "jsonl"] },
  { id: "feather", label: "Feather / Arrow",  extensions: ["feather", "arrow"] },
  { id: "numpy",   label: "NumPy",             extensions: ["npy", "npz"] },
  { id: "hdf5",    label: "HDF5",              extensions: ["h5", "hdf5"] },
  { id: "matlab",  label: "MATLAB",            extensions: ["mat"] },
  { id: "netcdf",  label: "NetCDF",            extensions: ["nc", "nc4", "cdf"] },
  { id: "fits",    label: "FITS",              extensions: ["fits", "fit", "fts"] },
];

function _detectConnector(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  for (const c of _CONNECTORS) {
    if (c.extensions.includes(ext)) return c.id;
  }
  return "csv";  // safe default — CSV connector has an auto-sniff path
}

function _basenameNoExt(path: string): string {
  // Strip trailing slash, take last component, strip last extension. Works
  // for both POSIX (`/a/b/c.csv`) and Windows-style (`C:\a\b\c.csv`) paths.
  const trimmed = path.replace(/[/\\]+$/, "");
  const last = trimmed.split(/[/\\]/).pop() ?? trimmed;
  const dot = last.lastIndexOf(".");
  return dot > 0 ? last.slice(0, dot) : last;
}

export function ReferenceFileModal({ open, onClose, onCreated, initialPath = "" }: Props) {
  const reduce = useReducedMotion();
  const qc = useQueryClient();

  // The path the user has currently selected (or typed). Empty until they
  // pick something; submit is disabled while empty.
  const [path, setPath] = useState<string>(initialPath);
  const [name, setName] = useState<string>("");
  const [connector, setConnector] = useState<string>("");
  // Auto-detected connector vs. the user's manual override; track the last
  // path we auto-detected from so re-typing doesn't keep clobbering an
  // explicit choice.
  const [autoConnectorForPath, setAutoConnectorForPath] = useState<string>("");

  // Browser state — the folder currently shown.
  const [browseAt, setBrowseAt] = useState<string>("");

  // Reset state every time the modal opens.
  useEffect(() => {
    if (open) {
      setPath(initialPath);
      setName(initialPath ? _basenameNoExt(initialPath) : "");
      const c = initialPath ? _detectConnector(initialPath) : "csv";
      setConnector(c);
      setAutoConnectorForPath(initialPath);
      setBrowseAt(initialPath || "");
    }
  }, [open, initialPath]);

  // When the user picks (or types) a new path, autofill name + connector.
  // Only re-derive the connector if the path itself changed since the last
  // auto-derivation — that way an explicit override survives further typing.
  useEffect(() => {
    if (!path) return;
    if (path !== autoConnectorForPath) {
      setName((cur) => cur || _basenameNoExt(path));
      setConnector(_detectConnector(path));
      setAutoConnectorForPath(path);
    }
  }, [path, autoConnectorForPath]);

  // Server-side directory listing — renders the browse pane. Re-runs on
  // every navigation. Cached short-term so click-clicking back-and-forth
  // doesn't refetch unnecessarily.
  const browseQ = useQuery<FsBrowseResult>({
    queryKey: ["fs-browse", browseAt],
    queryFn: () => api.browseDir(browseAt),
    enabled: open,
    staleTime: 5_000,
  });

  const submit = useMutation({
    mutationFn: async () => {
      if (!path || !name || !connector) throw new Error("path / name / connector required");
      // The backend's from-uri handler accepts ``file://`` URIs. Wrap the
      // raw path so it's unambiguous (a bare ``/foo`` would otherwise be
      // interpreted as URL-relative).
      const uri = path.startsWith("file://") ? path : `file://${path}`;
      return await api.createDatasetFromUri(name.trim(), connector, uri, {});
    },
    onSuccess: (ds) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      toast.success(`📁 Referenced "${ds.name}"`, {
        description: "Original file is preserved at its source location — DIG will not modify or delete it.",
      });
      onCreated?.(ds);
      onClose();
    },
    onError: (e) => {
      // Surface the backend's ValidationError text rather than a generic toast.
      if (e instanceof ApiError) {
        toastError("Reference failed", e);
      } else {
        toast.error(`Reference failed: ${(e as Error).message}`);
      }
    },
  });

  // Sort: directories first, then files; alphabetical within each.
  const entries = useMemo(() => {
    const list = [...(browseQ.data?.entries ?? [])];
    list.sort((a, b) => {
      if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    return list;
  }, [browseQ.data?.entries]);

  if (!open) return null;

  const fadeUp = reduce
    ? { initial: false, animate: { opacity: 1, scale: 1 } }
    : {
        initial: { opacity: 0, scale: 0.97 },
        animate: { opacity: 1, scale: 1 },
        exit: { opacity: 0, scale: 0.97 },
        transition: { type: "spring" as const, stiffness: 360, damping: 32 },
      };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reffile-title"
      >
        <motion.div
          {...fadeUp}
          className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        >
          <header className="flex items-center justify-between px-5 py-3 border-b border-border">
            <div>
              <h2 id="reffile-title" className="text-base font-semibold flex items-center gap-2">
                📁 Reference an existing file
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Adds the file as an input reference. Nothing is copied or moved.
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">✕</Button>
          </header>

          <div className="px-5 py-4 flex flex-col gap-4 overflow-y-auto">
            {/* Path field — typed or filled from the browser below */}
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                File path
              </span>
              <input
                type="text"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/absolute/path/to/data.parquet"
                className="rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
                autoFocus
              />
              <span className="text-[11px] text-muted-foreground">
                Absolute path on the DIG server. The file stays where it is — DIG only stores a pointer.
              </span>
            </label>

            {/* Inline file browser */}
            <div className="border border-border rounded-md flex flex-col">
              <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted/30">
                <span className="text-xs font-medium text-muted-foreground">Browse:</span>
                <input
                  type="text"
                  value={browseAt}
                  onChange={(e) => setBrowseAt(e.target.value)}
                  placeholder={browseQ.data?.home ?? "/"}
                  className="flex-1 rounded border border-input bg-background px-2 py-1 text-xs font-mono"
                />
                {browseQ.data?.parent && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setBrowseAt(browseQ.data!.parent!)}
                    title="Up one level"
                  >
                    ⬆️
                  </Button>
                )}
              </div>
              <div className="max-h-[260px] overflow-auto">
                {browseQ.isLoading && (
                  <p className="text-xs text-muted-foreground text-center py-6">Loading…</p>
                )}
                {browseQ.isError && (
                  <p className="text-xs text-destructive text-center py-6 px-3">
                    Browse failed: {(browseQ.error as Error).message}
                  </p>
                )}
                {browseQ.data && entries.length === 0 && (
                  <p className="text-xs text-muted-foreground text-center py-6">(empty directory)</p>
                )}
                {entries.map((e) => {
                  const fullPath = browseQ.data!.path.replace(/\/$/, "") + "/" + e.name;
                  const isSelected = !e.is_dir && fullPath === path;
                  return (
                    <button
                      key={e.name}
                      type="button"
                      onClick={() => {
                        if (e.is_dir) setBrowseAt(fullPath);
                        else setPath(fullPath);
                      }}
                      className={`w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 hover:bg-muted/50 ${
                        isSelected ? "bg-emerald-500/10 ring-1 ring-emerald-500/40" : ""
                      }`}
                    >
                      <span aria-hidden className="w-4 text-center">
                        {e.is_dir ? "📂" : "📄"}
                      </span>
                      <span className="font-mono text-xs truncate">{e.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Name + connector — auto-filled from path, overridable */}
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Display name
                </span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="my-dataset"
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Format
                </span>
                <select
                  value={connector}
                  onChange={(e) => setConnector(e.target.value)}
                  className="rounded-md border border-input bg-background px-2 py-2 text-sm"
                >
                  {_CONNECTORS.map((c) => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <footer className="flex items-center justify-between gap-2 px-5 py-3 border-t border-border bg-muted/20">
            <p className="text-[11px] text-muted-foreground">
              The original file is never modified or deleted by DIG.
            </p>
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={onClose} disabled={submit.isPending}>
                Cancel
              </Button>
              <Button
                onClick={() => submit.mutate()}
                disabled={!path || !name || submit.isPending}
              >
                {submit.isPending ? "Referencing…" : "📁 Reference file"}
              </Button>
            </div>
          </footer>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

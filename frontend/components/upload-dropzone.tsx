"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { motion, useReducedMotion } from "motion/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError, type Dataset } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { toastError } from "@/lib/toast-error";
import { SheetPickerModal } from "@/components/sheet-picker-modal";
import { IslandPickerModal } from "@/components/island-picker-modal";

interface Props {
  onUploaded?: (d: Dataset) => void;
}

export function UploadDropzone({ onUploaded }: Props) {
  const reduce = useReducedMotion();
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<string | null>(null);
  // When a multi-sheet workbook is uploaded the backend pauses ingest
  // and returns status='awaiting_sheet_pick' + availableSheets. We hold
  // the in-flight dataset here and render the sheet picker; on submit
  // the picker calls PUT /datasets/{id}/sheet which triggers ingest.
  const [awaitingSheet, setAwaitingSheet] = useState<Dataset | null>(null);
  // Same shape for the multi-island case — fires when the chosen sheet
  // (or single sheet) has 2+ disjoint data tables.
  const [awaitingIsland, setAwaitingIsland] = useState<Dataset | null>(null);

  const upload = useMutation({
    mutationFn: async (file: File) => {
      setProgress(`Uploading ${file.name}…`);
      // Route by extension. The CSV connector handles tab-separated via
      // its delimiter='auto' sniffer, plus generic .dat / .data / .tab /
      // .psv. The Excel connector handles both .xlsx and .xls via the
      // calamine engine. JSON / Parquet / Feather and the scientific
      // formats (NumPy / HDF5 / MATLAB / NetCDF / FITS) each have their
      // own connectors. Anything else falls back to CSV with auto-detect —
      // we'd rather try than reject.
      const ext = (file.name.split(".").pop() || "").toLowerCase();
      const connectorId =
        ext === "xlsx" || ext === "xls" ? "excel" :
        ext === "json" || ext === "ndjson" ? "json" :
        ext === "parquet" || ext === "pq" ? "parquet" :
        ext === "feather" || ext === "arrow" ? "feather" :
        ext === "npy" || ext === "npz" ? "numpy" :
        ext === "h5" || ext === "hdf5" ? "hdf5" :
        ext === "mat" ? "matlab" :
        ext === "nc" || ext === "nc4" || ext === "cdf" ? "netcdf" :
        ext === "fits" || ext === "fit" || ext === "fts" ? "fits" :
        "csv";  // csv / tsv / txt / dat / data / tab / psv / unknown
      // Round-5 W3: try with the default ``error`` on-conflict policy
      // first. If the backend rejects with 409, surface a sonner
      // confirm: Replace vs Keep both vs Cancel.
      try {
        return await api.uploadDataset(file, file.name, connectorId, {}, "error");
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          const detail = e.detail as { code?: string; existingId?: string; message?: string } | undefined;
          if (detail?.code === "dataset_name_in_use") {
            const choice = await new Promise<"replace" | "allow" | null>((resolve) => {
              const id = toast.warning(`Dataset "${file.name}" already exists`, {
                description: detail.message ?? "Pick how to resolve.",
                action: { label: "Replace", onClick: () => { resolve("replace"); toast.dismiss(id); } },
                cancel: { label: "Keep both", onClick: () => { resolve("allow"); toast.dismiss(id); } },
                duration: 30_000,
                onDismiss: () => resolve(null),
                onAutoClose: () => resolve(null),
              });
            });
            if (!choice) throw e;
            return api.uploadDataset(file, file.name, connectorId, {}, choice);
          }
        }
        throw e;
      }
    },
    onSuccess: (d) => {
      setProgress(null);
      // Multi-sheet Excel branch: backend saved the file but didn't ingest
      // yet. Open the sheet picker; on submit, ingest may pause again at
      // multi-island and the next-stage handler picks that up.
      if (d.status === "awaiting_sheet_pick" && (d.availableSheets?.length ?? 0) > 0) {
        setAwaitingSheet(d);
        queryClient.invalidateQueries({ queryKey: ["datasets"] });
        return;
      }
      // Multi-island branch — fires when a sheet has 2+ disjoint tables.
      // Can happen on either a single-sheet workbook or after the user
      // picks a sheet via the sheet picker (the sheet-pick endpoint
      // re-runs island detection too).
      if (d.status === "awaiting_island_pick" && (d.availableIslands?.length ?? 0) > 0) {
        setAwaitingIsland(d);
        queryClient.invalidateQueries({ queryKey: ["datasets"] });
        return;
      }
      toast.success(`📥 Imported "${d.name}" (${d.rowCount?.toLocaleString() ?? "?"} rows)`);
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      onUploaded?.(d);
    },
    onError: (e: Error) => {
      setProgress(null);
      toastError("Import failed", e);
    },
  });

  // Round-5 W3: support multi-file drops. Each file becomes its own
  // dataset and we report progress one-by-one — DIG's downstream
  // "join two CSVs" flow becomes discoverable when the user actually
  // ends up with two datasets side by side in the catalog.
  const onDrop = useCallback(
    (files: File[]) => {
      if (files.length === 0) return;
      if (files.length === 1) {
        upload.mutate(files[0]);
        return;
      }
      // Serial upload: avoid hammering the backend's connector workers
      // in parallel; users dropping 4 files want them all ingested,
      // not 3 of 4 succeeding because of a transient backend load.
      (async () => {
        let succeeded = 0;
        for (const f of files) {
          try {
            await upload.mutateAsync(f);
            succeeded += 1;
          } catch (e) {
            toast.error(`Skipped ${f.name}: ${(e as Error).message}`);
          }
        }
        if (succeeded > 1) {
          toast.success(
            `Imported ${succeeded} datasets — open the catalog to join them.`,
            {
              action: {
                label: "Open catalog",
                onClick: () => { window.location.href = "/catalog"; },
              },
              duration: 6000,
            },
          );
        }
      })();
    },
    [upload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    // Accept the file types DIG's connectors handle out of the box.
    // The MIME type per format is intentionally generous — different OSes
    // disagree (text/tab-separated-values vs text/plain for .tsv, etc.),
    // so we lean on the extension lists which work cross-platform.
    accept: {
      "text/csv": [".csv"],
      "text/tab-separated-values": [".tsv", ".tab"],
      // Generic delimited-text formats — the CSV connector now sniffs
      // the delimiter, so .dat / .data scientific files come in cleanly.
      "text/plain": [".txt", ".dat", ".data", ".psv"],
      "application/vnd.ms-excel": [".xls"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/json": [".json", ".ndjson"],
      // application/octet-stream is the catch-all for binary formats with
      // no registered MIME type. Browsers report this for Parquet, Feather,
      // NumPy, HDF5, MATLAB, NetCDF, and FITS files.
      "application/octet-stream": [
        ".parquet", ".pq",
        ".feather", ".arrow",
        ".npy", ".npz",
        ".h5", ".hdf5",
        ".mat",
        ".nc", ".nc4", ".cdf",
        ".fits", ".fit", ".fts",
      ],
    },
    multiple: true,
    disabled: upload.isPending,
  });

  return (
    <>
      <div
        {...getRootProps()}
        className={cn(
          "relative cursor-pointer rounded-xl border-2 border-dashed transition-colors",
          "px-8 py-12 flex flex-col items-center justify-center gap-3 text-center",
          "bg-muted/20 hover:bg-muted/40",
          isDragActive ? "border-primary bg-primary/10" : "border-border",
          upload.isPending && "pointer-events-none opacity-70",
        )}
      >
        <input {...getInputProps()} />
        <motion.div
          key={isDragActive ? "drag" : upload.isPending ? "wait" : "idle"}
          initial={reduce ? false : { scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 280, damping: 22 }}
          className="text-5xl select-none"
          role="img"
          aria-label="Upload"
        >
          {upload.isPending ? "⏳" : isDragActive ? "📥" : "📄"}
        </motion.div>
        <div>
          <p className="text-sm font-medium">
            {upload.isPending
              ? progress
              : isDragActive
                ? "Drop to ingest"
                : "Drop a file here, or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            CSV · TSV · TXT · DAT · DATA · TAB · PSV · XLSX · XLS · JSON · Parquet · Feather · NumPy · HDF5 · MATLAB · NetCDF · FITS
          </p>
          <p className="text-[10px] text-muted-foreground/70 mt-0.5">
            Auto-detects header + delimiter for text files. Scientific binary formats need the <code>[science]</code> backend extra.
          </p>
        </div>
      </div>

      {awaitingSheet && (
        <SheetPickerModal
          dataset={awaitingSheet}
          onPicked={(next) => {
            setAwaitingSheet(null);
            queryClient.invalidateQueries({ queryKey: ["datasets"] });
            // Two-stage UX: picking a sheet may itself unmask a
            // multi-island situation. Chain into the island picker.
            if (next.status === "awaiting_island_pick") {
              setAwaitingIsland(next);
              return;
            }
            if (next.status === "ready") onUploaded?.(next);
          }}
          onCancel={() => {
            toast.info("Sheet pick deferred — dataset stays as 'awaiting sheet pick'. Open from the datasets list to resume.");
            setAwaitingSheet(null);
            queryClient.invalidateQueries({ queryKey: ["datasets"] });
          }}
        />
      )}

      {awaitingIsland && (
        <IslandPickerModal
          dataset={awaitingIsland}
          onPicked={(next) => {
            setAwaitingIsland(null);
            queryClient.invalidateQueries({ queryKey: ["datasets"] });
            if (next.status === "ready") onUploaded?.(next);
          }}
          onCancel={() => {
            toast.info("Island pick deferred — dataset stays as 'awaiting island pick'. Open from the datasets list to resume.");
            setAwaitingIsland(null);
            queryClient.invalidateQueries({ queryKey: ["datasets"] });
          }}
        />
      )}
    </>
  );
}

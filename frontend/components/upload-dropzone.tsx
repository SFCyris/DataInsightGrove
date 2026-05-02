"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { motion, useReducedMotion } from "motion/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Dataset } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface Props {
  onUploaded?: (d: Dataset) => void;
}

export function UploadDropzone({ onUploaded }: Props) {
  const reduce = useReducedMotion();
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async (file: File) => {
      setProgress(`Uploading ${file.name}…`);
      return api.uploadDataset(file, file.name);
    },
    onSuccess: (d) => {
      setProgress(null);
      toast.success(`📥 Imported "${d.name}" (${d.rowCount?.toLocaleString() ?? "?"} rows)`);
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      onUploaded?.(d);
    },
    onError: (e: Error) => {
      setProgress(null);
      toast.error(`Import failed: ${e.message}`);
    },
  });

  const onDrop = useCallback(
    (files: File[]) => {
      if (files[0]) upload.mutate(files[0]);
    },
    [upload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv", ".tsv", ".txt"],
      "application/vnd.ms-excel": [".csv"],
    },
    multiple: false,
    disabled: upload.isPending,
  });

  return (
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
              : "Drop a CSV here, or click to browse"}
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          .csv · .tsv · .txt — UTF-8 by default
        </p>
      </div>
    </div>
  );
}

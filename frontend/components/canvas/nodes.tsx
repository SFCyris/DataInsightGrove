"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "motion/react";

const CATEGORY_EMOJI: Record<string, string> = {
  ingest: "📥",
  shape: "✂️",
  clean: "🧹",
  derive: "➕",
  combine: "🔗",
  aggregate: "📊",
  model: "🧠",
  output: "📤",
  custom: "🧩",
};

export interface DatasetNodeData extends Record<string, unknown> {
  kind: "dataset";
  label: string;
  connector: string;
  uri: string;
}

export interface StepNodeData extends Record<string, unknown> {
  kind: "step";
  label: string;
  category: string;
  step: string;
  inputPorts: string[];
  outputPorts: string[];
  hasError?: boolean;
}

export interface OutputNodeData extends Record<string, unknown> {
  kind: "output";
  label: string;
  sink?: string | null;
}

export function DatasetNode({ data, selected }: NodeProps) {
  const d = data as DatasetNodeData;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      className={[
        "min-w-[180px] rounded-lg border bg-card px-3 py-2 shadow-sm",
        selected ? "border-foreground/50 ring-2 ring-ring/40" : "border-border",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="text-base" aria-hidden>📊</span>
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Dataset</p>
          <p className="text-sm font-medium truncate" title={d.label}>{d.label}</p>
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="out" className="!bg-foreground/40" />
    </motion.div>
  );
}

export function StepNode({ data, selected }: NodeProps) {
  const d = data as StepNodeData;
  const emoji = CATEGORY_EMOJI[d.category] ?? "🧩";
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      className={[
        "min-w-[200px] rounded-lg border bg-card px-3 py-2 shadow-sm",
        selected ? "border-foreground/50 ring-2 ring-ring/40" : "border-border",
        d.hasError ? "border-destructive/60" : "",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="text-base" aria-hidden>{emoji}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{d.category}</p>
          <p className="text-sm font-medium truncate">{d.label}</p>
        </div>
        {d.hasError && <span title="Validation error">⚠️</span>}
      </div>

      {d.inputPorts.map((port, idx) => (
        <Handle
          key={`in-${port}`}
          type="target"
          id={port}
          position={Position.Left}
          style={{ top: 24 + idx * 16 }}
          className="!bg-foreground/40"
        />
      ))}
      {d.outputPorts.map((port, idx) => (
        <Handle
          key={`out-${port}`}
          type="source"
          id={port}
          position={Position.Right}
          style={{ top: 24 + idx * 16 }}
          className="!bg-foreground/40"
        />
      ))}
    </motion.div>
  );
}

export function OutputNode({ data, selected }: NodeProps) {
  const d = data as OutputNodeData;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      className={[
        "min-w-[160px] rounded-lg border-2 border-dashed px-3 py-2",
        selected ? "border-foreground/60 ring-2 ring-ring/40" : "border-border",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span className="text-base" aria-hidden>📤</span>
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Output</p>
          <p className="text-sm font-medium truncate">{d.label}</p>
        </div>
      </div>
      <Handle type="target" position={Position.Left} id="out" className="!bg-foreground/40" />
    </motion.div>
  );
}

export const nodeTypes = {
  dataset: DatasetNode,
  step: StepNode,
  output: OutputNode,
};

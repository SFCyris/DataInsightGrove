"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { PositiveLoader } from "@/components/positive-loader";

interface Props {
  pipelineId: string;
  open: boolean;
  onClose: () => void;
  /** Currently focused step — used as the SQL terminal (compile up to here). */
  terminal?: string | null;
}

/**
 * Live SQL view (Tier 1 — read-only).
 *
 * Engineer-mode flagship. Shows the compiled DuckDB SQL the entire pipeline
 * runs as. Each CTE is annotated with the originating node id + label so
 * the user can match SQL ↔ visual nodes by eye.
 *
 * Tier 2 (round-trip parse) and Tier 3 (custom_sql step) ship in a follow-up.
 */
export function SqlView({ pipelineId, open, onClose, terminal }: Props) {
  const reduce = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const compileQ = useQuery({
    queryKey: ["compile-sql", pipelineId, terminal ?? "all"],
    queryFn: () => api.fetchCompile(pipelineId, 100_000, terminal ?? undefined),
    enabled: open,
  });

  const sql = compileQ.data?.sql ?? "";

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.aside
            initial={reduce ? { opacity: 0 } : { y: "100%" }}
            animate={reduce ? { opacity: 1 } : { y: 0 }}
            exit={reduce ? { opacity: 0 } : { y: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="fixed left-0 right-0 bottom-0 z-50 h-[70vh] bg-background border-t border-border shadow-2xl flex flex-col"
            role="dialog"
            aria-label="Compiled SQL view"
          >
            <header className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/40">
              <span className="text-xl select-none" aria-hidden>{"{ }"}</span>
              <div className="flex-1 min-w-0">
                <h2 className="text-sm font-semibold tracking-tight">Compiled SQL</h2>
                <p className="text-[10px] text-muted-foreground tabular-nums">
                  {compileQ.data
                    ? `${sql.length.toLocaleString()} chars · ${(compileQ.data.files?.length ?? 0)} dataset bindings`
                    : "Compiling…"}
                  {terminal ? ` · terminal #${terminal.slice(-8)}` : " · full pipeline"}
                </p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  if (!sql) return;
                  try {
                    await navigator.clipboard.writeText(sql);
                    toast.success("📋 Copied SQL to clipboard");
                  } catch {
                    toast.error("Couldn't copy — your browser blocked clipboard.");
                  }
                }}
                disabled={!sql}
              >
                📋 Copy
              </Button>
              <button
                type="button"
                onClick={onClose}
                className="text-xs text-muted-foreground hover:text-foreground rounded px-2 py-1 hover:bg-muted"
              >
                ✕
              </button>
            </header>

            <div className="flex-1 overflow-auto p-4">
              {compileQ.isLoading && (
                <div className="grid place-items-center py-8">
                  <PositiveLoader variant="compiling" />
                </div>
              )}
              {compileQ.error && (
                <p className="text-sm text-destructive">
                  Compile failed: {(compileQ.error as Error).message}
                </p>
              )}
              {sql && <SqlPretty sql={sql} />}
            </div>
            <footer className="px-4 py-2 border-t border-border text-[10px] text-muted-foreground tabular-nums">
              <span>This is the exact query DIG will hand to DuckDB. </span>
              <span className="text-muted-foreground/70">
                Tier 2 round-trip edit and `🌳 SQL step` ship in a follow-up.
              </span>
            </footer>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

// Lightweight SQL "highlighter": tints keywords + CTE-header comments
// without pulling in CodeMirror. Visual aid only; non-interactive.
function SqlPretty({ sql }: { sql: string }) {
  const lines = sql.split("\n");
  return (
    <pre className="text-[11px] leading-relaxed font-mono tabular-nums whitespace-pre-wrap rounded-lg border border-border bg-card/40 p-3">
      {lines.map((line, i) => (
        <SqlLine key={i} line={line} />
      ))}
    </pre>
  );
}

const KEYWORDS = new Set([
  "WITH",
  "SELECT",
  "FROM",
  "WHERE",
  "GROUP",
  "BY",
  "ORDER",
  "HAVING",
  "JOIN",
  "LEFT",
  "RIGHT",
  "INNER",
  "OUTER",
  "FULL",
  "ON",
  "AS",
  "AND",
  "OR",
  "NOT",
  "IS",
  "NULL",
  "DISTINCT",
  "LIMIT",
  "OFFSET",
  "UNION",
  "ALL",
  "CASE",
  "WHEN",
  "THEN",
  "ELSE",
  "END",
  "OVER",
  "PARTITION",
  "RENAME",
]);

function SqlLine({ line }: { line: string }) {
  const trimmed = line.trim();
  if (trimmed.startsWith("--")) {
    return (
      <span className="text-muted-foreground/80">
        {line}
        {"\n"}
      </span>
    );
  }
  // Pre-extract single-quoted string literals first so we don't keyword-tint
  // identifiers that happen to live inside a string (e.g. `'END OF FILE'`
  // would have made the `END` token render as a violet keyword).
  const segments: Array<{ text: string; inString: boolean }> = [];
  let i = 0;
  while (i < line.length) {
    const ch = line[i];
    if (ch === "'") {
      let j = i + 1;
      while (j < line.length) {
        if (line[j] === "'" && line[j + 1] === "'") {
          j += 2; // SQL-style escaped quote
          continue;
        }
        if (line[j] === "'") {
          j += 1;
          break;
        }
        j += 1;
      }
      segments.push({ text: line.slice(i, j), inString: true });
      i = j;
    } else {
      let j = i;
      while (j < line.length && line[j] !== "'") j += 1;
      segments.push({ text: line.slice(i, j), inString: false });
      i = j;
    }
  }
  return (
    <>
      {segments.flatMap((seg, segIdx) => {
        if (seg.inString) {
          return [
            <span key={`s${segIdx}`} className="text-amber-700 dark:text-amber-300">
              {seg.text}
            </span>,
          ];
        }
        // Tokenize on whitespace + punctuation, preserve original spacing.
        const tokens = seg.text.split(/(\s+|[(),;])/);
        return tokens.map((t, i) => {
          const u = t.toUpperCase();
          if (KEYWORDS.has(u)) {
            return (
              <span key={`${segIdx}-${i}`} className="text-violet-700 dark:text-violet-300 font-semibold">
                {t}
              </span>
            );
          }
          if (t.startsWith('"') && t.endsWith('"') && t.length > 2) {
            return (
              <span key={`${segIdx}-${i}`} className="text-emerald-700 dark:text-emerald-400">
                {t}
              </span>
            );
          }
          return <span key={`${segIdx}-${i}`}>{t}</span>;
        });
      })}
      {"\n"}
    </>
  );
}

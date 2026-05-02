"use client";

import { motion } from "motion/react";
import { api } from "@/lib/api/client";
import { fmtInt } from "@/lib/format-number";

// The artifacts payload comes through as a free-form JSON dict from the
// backend (OpenAPI types it as `{ [k: string]: unknown }`). We narrow at
// the use sites instead of demanding a strict prop type.
type Artifact = { kind?: string; [k: string]: unknown };

interface Props {
  runId: string;
  /** Map of output id -> artifact list, as returned by RunOut.artifacts. */
  artifacts: Record<string, Array<{ [k: string]: unknown }>>;
}

function fmtBytes(n: number | undefined): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function ArtifactsPanel({ runId, artifacts }: Props) {
  const flat: Artifact[] = Object.values(artifacts).flat();
  if (flat.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="border-t border-border bg-muted/20 px-4 py-3"
    >
      <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
        🎁 Run artifacts
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {flat.map((a, i) => {
          if (a.kind === "image" && "path" in a && a.path) {
            const url = api.artifactUrl(runId, String(a.path));
            return (
              <a
                key={i}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="group rounded-lg border border-border bg-card overflow-hidden hover:border-foreground/40 transition-colors"
              >
                <div className="aspect-[3/2] bg-background grid place-items-center overflow-hidden">
                  <img
                    src={url}
                    alt={(a as { title?: string }).title ?? "render"}
                    className="object-contain w-full h-full"
                  />
                </div>
                <div className="px-3 py-2 text-xs">
                  <p className="font-medium flex items-center gap-1.5">
                    <span aria-hidden>🖼</span>
                    {(a as { title?: string }).title ?? (a as { chart?: string }).chart ?? "image"}
                  </p>
                  <p className="text-muted-foreground text-[10px] tabular-nums">
                    {(a as { chart?: string }).chart}
                    {(a as { rows_plotted?: number }).rows_plotted != null &&
                      ` · ${fmtInt((a as { rows_plotted: number }).rows_plotted)} pts`}
                  </p>
                </div>
              </a>
            );
          }
          if (a.kind === "file" && "path" in a) {
            const url = api.artifactUrl(runId, String(a.path));
            return (
              <a
                key={i}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-border bg-card p-3 text-xs hover:border-foreground/40 transition-colors flex items-center gap-3"
              >
                <span className="text-2xl" aria-hidden>📄</span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">{(a as { format?: string }).format?.toUpperCase()} export</p>
                  <p className="text-muted-foreground text-[10px] truncate" title={String(a.path)}>
                    {String(a.path).split("/").slice(-1)[0]}
                  </p>
                  <p className="text-muted-foreground text-[10px] tabular-nums">
                    {fmtInt((a as { rows?: number }).rows)} rows
                    {(a as { size?: number }).size != null && ` · ${fmtBytes((a as { size: number }).size)}`}
                  </p>
                </div>
                <span className="text-muted-foreground/60">↓</span>
              </a>
            );
          }
          if (a.kind === "db") {
            return (
              <div key={i} className="rounded-lg border border-border bg-card p-3 text-xs flex items-center gap-3">
                <span className="text-2xl" aria-hidden>🗃</span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">DB write → {(a as { table?: string }).table}</p>
                  <p className="text-muted-foreground text-[10px] truncate font-mono">
                    {(a as { uri?: string }).uri}
                  </p>
                  <p className="text-muted-foreground text-[10px] tabular-nums">
                    {fmtInt((a as { rows?: number }).rows)} rows ·{" "}
                    {(a as { if_exists?: string }).if_exists}
                  </p>
                </div>
              </div>
            );
          }
          if (a.kind === "sink") {
            return (
              <div key={i} className="rounded-lg border border-border bg-card p-3 text-xs flex items-center gap-3">
                <span className="text-2xl" aria-hidden>📤</span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">
                    Sink → {(a as { connector?: string }).connector}
                  </p>
                  <p className="text-muted-foreground text-[10px] truncate font-mono">
                    {(a as { uri?: string }).uri}
                  </p>
                </div>
              </div>
            );
          }
          if (a.kind === "stats") {
            const label = (a as { label?: string }).label ?? "Stats";
            const data = (a as { data?: Record<string, unknown> }).data ?? {};
            return (
              <div key={i} className="rounded-lg border border-border bg-card p-3 text-xs col-span-1 sm:col-span-2 lg:col-span-3">
                <p className="font-medium flex items-center gap-1.5 mb-1.5">
                  <span aria-hidden>📈</span>{label}
                </p>
                <pre className="text-[10px] text-muted-foreground bg-background/50 p-2 rounded overflow-auto max-h-40">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </div>
            );
          }
          if (a.kind === "expectations") {
            type Result = { rule: { kind: string; column?: string }; passed?: boolean; violations?: number; nulls?: number; duplicates?: number; error?: string };
            const results = ((a as { results?: Result[] }).results ?? []);
            const nFailed = (a as { n_failed?: number }).n_failed ?? results.filter((r) => !r.passed).length;
            const nRules = (a as { n_rules?: number }).n_rules ?? results.length;
            return (
              <div key={i} className="rounded-lg border border-border bg-card p-3 text-xs col-span-1 sm:col-span-2 lg:col-span-3">
                <p className="font-medium flex items-center gap-1.5 mb-1.5">
                  <span aria-hidden>{nFailed === 0 ? "✅" : "❌"}</span>
                  Data quality · {nRules - nFailed}/{nRules} rules passed
                </p>
                <ul className="space-y-1 text-[11px]">
                  {results.map((r, idx) => (
                    <li
                      key={idx}
                      className={
                        "flex items-start gap-2 py-0.5 " +
                        (r.passed ? "text-muted-foreground" : "text-red-600 dark:text-red-400")
                      }
                    >
                      <span aria-hidden>{r.passed ? "•" : "✗"}</span>
                      <span className="flex-1">
                        <span className="font-mono">{r.rule.kind}</span>
                        {r.rule.column ? <> · <span className="font-mono">{r.rule.column}</span></> : null}
                        {r.violations != null ? <> · {r.violations} violations</> : null}
                        {r.nulls != null ? <> · {r.nulls} nulls</> : null}
                        {r.duplicates != null ? <> · {r.duplicates} duplicates</> : null}
                        {r.error ? <> · {r.error}</> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          }
          if (a.kind === "subpipeline") {
            return (
              <div key={i} className="rounded-lg border border-border bg-card p-3 text-xs flex items-center gap-3">
                <span className="text-2xl" aria-hidden>🧩</span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">
                    Sub-pipeline · {(a as { pipeline_name?: string }).pipeline_name}
                  </p>
                  <p className="text-muted-foreground text-[10px] truncate font-mono">
                    {(a as { pipeline_id?: string }).pipeline_id}
                  </p>
                  <p className="text-muted-foreground text-[10px] tabular-nums">
                    {fmtInt((a as { rows?: number }).rows)} rows
                  </p>
                </div>
              </div>
            );
          }
          // unknown / future kinds
          return (
            <pre
              key={i}
              className="rounded-lg border border-border bg-card p-3 text-[10px] overflow-auto"
            >
              {JSON.stringify(a, null, 2)}
            </pre>
          );
        })}
      </div>
    </motion.section>
  );
}

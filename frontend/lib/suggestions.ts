/**
 * Rule-based suggestion engine — pure functions over the column profile.
 *
 * These are deterministic heuristic hints rendered in a static side panel;
 * they are NOT ML predictions, NOT triggered by cell/range selection, and
 * NOT presented as ranked browsable cards. The hints just surface things
 * the profile already knows ("this column is 30% null — drop nulls?") in a
 * single, calm place.
 *
 * Each suggestion proposes ONE concrete column action — the user clicks
 * "Apply" and the editor adds the corresponding step. Undo is one keystroke.
 */

import type { ColumnAction } from "@/components/canvas/column-menu";

export type SuggestionSeverity = "info" | "tip" | "warn";

export interface Suggestion {
  id: string;
  severity: SuggestionSeverity;
  emoji: string;
  title: string;
  body: string;
  /** The column this suggestion is about — for highlighting in the grid. */
  column: string;
  /** Action that gets applied if the user clicks "Apply". */
  action: ColumnAction;
  /** Short label shown on the Apply button. */
  applyLabel: string;
}

interface ColumnLike {
  name: string;
  type: string;
  nullCount?: number | null;
  nullFraction?: number | null;
  distinctCount?: number | null;
  sampledRows?: number | null;
  topValues?: Array<{ value: unknown; count: number }>;
  min?: unknown;
  max?: unknown;
}

function logical(t: string): string {
  const m = (t || "").toLowerCase();
  if (m.startsWith("int") || m === "bigint") return "integer";
  if (m === "double" || m === "float" || m === "float32" || m === "float64" || m.includes("decimal")) return "double";
  if (m.startsWith("bool")) return "boolean";
  if (m === "date") return "date";
  if (m.startsWith("timestamp") || m === "datetime") return "datetime";
  return "string";
}

const DATE_LIKE_RE = /^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$/;
const NUM_LIKE_RE = /^-?\d+(?:\.\d+)?$/;
const BOOL_LIKE_RE = /^(true|false|yes|no|y|n|0|1)$/i;
const EMAIL_LIKE_RE = /@/;

/** Inspect the profile for a single column and emit any applicable hints. */
export function suggestForColumn(c: ColumnLike): Suggestion[] {
  const out: Suggestion[] = [];
  const t = logical(c.type);

  // 1. High null rate → suggest filter-out-nulls.
  if (c.nullFraction != null && c.nullFraction >= 0.05) {
    const pct = `${(c.nullFraction * 100).toFixed(c.nullFraction < 0.1 ? 1 : 0)}%`;
    out.push({
      id: `nulls:${c.name}`,
      severity: c.nullFraction >= 0.25 ? "warn" : "tip",
      emoji: c.nullFraction >= 0.25 ? "🟡" : "🟢",
      title: `${pct} nulls in ${c.name}`,
      body: `${c.nullCount?.toLocaleString() ?? "?"} of ${c.sampledRows?.toLocaleString() ?? "?"} sampled rows are NULL.`,
      column: c.name,
      action: { kind: "filter_notnull", column: c.name },
      applyLabel: `Filter out NULLs`,
    });
  }

  // 2. String column that *looks like* dates → suggest cast to date.
  if (t === "string" && c.topValues?.length) {
    const samples = c.topValues.slice(0, 5).map((v) => String(v.value ?? "")).filter(Boolean);
    if (samples.length >= 2 && samples.every((s) => DATE_LIKE_RE.test(s))) {
      out.push({
        id: `date-cast:${c.name}`,
        severity: "tip",
        emoji: "📅",
        title: `${c.name} looks like dates`,
        body: `Top values match a date pattern (e.g. "${samples[0]}"). Casting unlocks date-aware operations.`,
        column: c.name,
        action: { kind: "cast", column: c.name, targetType: "date" },
        applyLabel: "Cast → date",
      });
    } else if (samples.length >= 2 && samples.every((s) => NUM_LIKE_RE.test(s))) {
      out.push({
        id: `num-cast:${c.name}`,
        severity: "tip",
        emoji: "🔢",
        title: `${c.name} looks numeric`,
        body: `Top values are all numbers — currently stored as strings.`,
        column: c.name,
        action: { kind: "cast", column: c.name, targetType: "double" },
        applyLabel: "Cast → number",
      });
    } else if (samples.length >= 2 && samples.every((s) => BOOL_LIKE_RE.test(s))) {
      out.push({
        id: `bool-cast:${c.name}`,
        severity: "tip",
        emoji: "☑️",
        title: `${c.name} looks like booleans`,
        body: `Values are true/false-ish.`,
        column: c.name,
        action: { kind: "cast", column: c.name, targetType: "boolean" },
        applyLabel: "Cast → boolean",
      });
    }
  }

  // 3. Low-cardinality string → suggest "Group by".
  if (
    t === "string" &&
    c.distinctCount != null &&
    c.sampledRows != null &&
    c.sampledRows > 0 &&
    c.distinctCount > 1 &&
    c.distinctCount <= Math.max(20, c.sampledRows * 0.05) &&
    !c.name.toLowerCase().endsWith("id") &&
    !(c.topValues?.[0]?.value && EMAIL_LIKE_RE.test(String(c.topValues[0].value)))
  ) {
    out.push({
      id: `groupby:${c.name}`,
      severity: "info",
      emoji: "📊",
      title: `Group by ${c.name}?`,
      body: `${c.distinctCount} distinct values out of ${c.sampledRows.toLocaleString()} sampled rows — looks categorical.`,
      column: c.name,
      action: { kind: "group_by", column: c.name },
      applyLabel: "Group by",
    });
  }

  // 4. Numeric column with one unique value → likely useless, suggest drop.
  if ((t === "integer" || t === "double") && c.distinctCount === 1) {
    out.push({
      id: `drop-constant:${c.name}`,
      severity: "tip",
      emoji: "✂️",
      title: `${c.name} is constant`,
      body: `Only one distinct value in the sample. Likely safe to drop.`,
      column: c.name,
      action: { kind: "drop", column: c.name },
      applyLabel: "Drop column",
    });
  }

  // 5. ID-named column with high cardinality → suggest sort by it (often handy for joins/inspection).
  if (
    (t === "integer" || t === "string") &&
    /(_id|^id)$/i.test(c.name) &&
    c.distinctCount != null &&
    c.sampledRows != null &&
    c.distinctCount >= c.sampledRows * 0.9
  ) {
    out.push({
      id: `sort-id:${c.name}`,
      severity: "info",
      emoji: "↕️",
      title: `Sort by ${c.name}?`,
      body: `Looks like an identifier (≥90% distinct).`,
      column: c.name,
      action: { kind: "sort", column: c.name, direction: "asc" },
      applyLabel: "Sort ascending",
    });
  }

  return out;
}

export function suggestionsFromProfile(columns: ColumnLike[]): Suggestion[] {
  const all: Suggestion[] = [];
  for (const c of columns) all.push(...suggestForColumn(c));
  // Deterministic ordering: warn → tip → info; then by column name.
  const rank: Record<SuggestionSeverity, number> = { warn: 0, tip: 1, info: 2 };
  return all.sort((a, b) => rank[a.severity] - rank[b.severity] || a.column.localeCompare(b.column));
}

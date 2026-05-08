"use client";

/**
 * ResultColumnsPanel — the "what comes out of the join" panel.
 *
 * Closes the intuition gap that joins have: once the user picks keys,
 * the natural next question is "which columns, at what names, will I
 * see downstream?". The panel answers that with a glanceable list:
 *
 *   ◖L◗ ☑ customer_id            int       (left)
 *   ◖L◗ ☑ name_left              string    ← name (left)
 *   ◖R◗ ☑ name_right             string    ← name (right)
 *   ◖C◗ ☑ price                  double    ← coalesced
 *
 * Each row encodes provenance four ways at once: the `L`/`R`/`C` chip,
 * the soft tinted background, the left-edge accent stripe, and the
 * subdued source-column label. The user can:
 *   - uncheck — drops the column from the output
 *   - rename  — changes the AS alias
 *
 * Duplicate-name guard: if two included columns end up with the same
 * final name, both rows turn rose and a banner asks the user to
 * resolve. We don't attempt to silently auto-rename — the user typed
 * a name; the user fixes it.
 *
 * The diff is stored on `params.outputColumns = { excluded, renames }`
 * keyed by stable provenance ID (`L:<src>`, `R:<src>`, `C:<src>`) so
 * collision-rule changes (which alter the default name) don't strand
 * user edits.
 */
import { useMemo } from "react";
import type { JoinKey } from "./join-keys-builder";
import type { RowSample } from "./match-quality";

type CollisionRule = "keep_both" | "keep_left" | "keep_right" | "coalesce";
type Side = "L" | "R" | "C";

export interface OutputColumnsValue {
  excluded: string[];
  renames: Record<string, string>;
}

interface Props {
  value: OutputColumnsValue;
  onChange: (next: OutputColumnsValue) => void;
  leftCols: string[];
  rightCols: string[];
  leftRows: RowSample[];
  rightRows: RowSample[];
  keys: JoinKey[];
  rule: CollisionRule;
  suffixes: [string, string];
  /** When the join is anti_left, only left columns survive; anti_right
   *  is the mirror. Other kinds project from both sides. */
  kind: string;
}

interface OutputCol {
  provId: string;          // "L:price" / "R:zipcode" / "C:name"
  side: Side;
  source: string;          // "price"
  defaultName: string;     // "price" or "price_left"
  type: string;            // "int" / "string" / "?" — sniffed from samples
}

/** Sniff a friendly type label from sampled values. Approximate but
 *  enough to colour-code on intent (number-ish vs string vs date). */
function sniffType(rows: RowSample[], col: string): string {
  for (const r of rows) {
    const v = r[col];
    if (v == null) continue;
    if (typeof v === "number") return Number.isInteger(v) ? "int" : "double";
    if (typeof v === "boolean") return "bool";
    if (typeof v === "string") {
      // Cheap date sniff (ISO-ish) — purely cosmetic, mistakes are fine.
      if (/^\d{4}-\d{2}-\d{2}/.test(v)) return "date";
      if (/^-?\d+$/.test(v)) return "int";
      if (/^-?\d+\.\d+$/.test(v)) return "double";
      return "string";
    }
    return "?";
  }
  return "?";
}

/** Build the canonical projection list — mirrors the backend's
 *  `_build_select_clause` order + naming exactly. */
function deriveOutputColumns(
  leftCols: string[],
  rightCols: string[],
  leftRows: RowSample[],
  rightRows: RowSample[],
  keys: JoinKey[],
  rule: CollisionRule,
  suffixes: [string, string],
  kind: string,
): OutputCol[] {
  // anti_left: left columns only (no collisions to worry about).
  if (kind === "anti_left") {
    return leftCols.map((col) => ({
      provId: `L:${col}`,
      side: "L" as const,
      source: col,
      defaultName: col,
      type: sniffType(leftRows, col),
    }));
  }
  if (kind === "anti_right") {
    return rightCols.map((col) => ({
      provId: `R:${col}`,
      side: "R" as const,
      source: col,
      defaultName: col,
      type: sniffType(rightRows, col),
    }));
  }

  const eqLeft = new Set(keys.filter((k) => (k.op ?? "=") === "=").map((k) => k.left));
  const eqRight = new Set(keys.filter((k) => (k.op ?? "=") === "=").map((k) => k.right));
  const leftSet = new Set(leftCols);
  const rightSet = new Set(rightCols);

  const out: OutputCol[] = [];

  for (const col of leftCols) {
    const t = sniffType(leftRows, col);
    if (rightSet.has(col) && !eqLeft.has(col)) {
      // collision
      if (rule === "keep_left") {
        out.push({ provId: `L:${col}`, side: "L", source: col, defaultName: col, type: t });
      } else if (rule === "keep_right") {
        // skip — the right loop emits this one
      } else if (rule === "coalesce") {
        out.push({ provId: `C:${col}`, side: "C", source: col, defaultName: col, type: t });
      } else {
        // keep_both
        out.push({
          provId: `L:${col}`,
          side: "L",
          source: col,
          defaultName: col + suffixes[0],
          type: t,
        });
      }
    } else {
      out.push({ provId: `L:${col}`, side: "L", source: col, defaultName: col, type: t });
    }
  }

  for (const col of rightCols) {
    if (eqRight.has(col)) continue; // collapsed equality-key right column
    const t = sniffType(rightRows, col);
    if (leftSet.has(col)) {
      if (rule === "keep_left" || rule === "coalesce") continue;
      if (rule === "keep_right") {
        out.push({ provId: `R:${col}`, side: "R", source: col, defaultName: col, type: t });
      } else {
        out.push({
          provId: `R:${col}`,
          side: "R",
          source: col,
          defaultName: col + suffixes[1],
          type: t,
        });
      }
    } else {
      out.push({ provId: `R:${col}`, side: "R", source: col, defaultName: col, type: t });
    }
  }

  return out;
}

const SIDE_STYLE: Record<Side, { label: string; chip: string; stripe: string; row: string; sub: string }> = {
  L: {
    label: "L",
    // light_blue background + dark_blue text → WCAG-AA legible
    chip: "bg-sky-200/80 text-sky-900 dark:bg-sky-900/50 dark:text-sky-100 ring-1 ring-sky-300/60 dark:ring-sky-700/40",
    stripe: "bg-sky-400 dark:bg-sky-500",
    row: "bg-sky-50/40 dark:bg-sky-950/20 hover:bg-sky-50/70 dark:hover:bg-sky-950/30",
    sub: "text-sky-700/70 dark:text-sky-300/70",
  },
  R: {
    label: "R",
    chip: "bg-emerald-200/80 text-emerald-900 dark:bg-emerald-900/50 dark:text-emerald-100 ring-1 ring-emerald-300/60 dark:ring-emerald-700/40",
    stripe: "bg-emerald-400 dark:bg-emerald-500",
    row: "bg-emerald-50/40 dark:bg-emerald-950/20 hover:bg-emerald-50/70 dark:hover:bg-emerald-950/30",
    sub: "text-emerald-700/70 dark:text-emerald-300/70",
  },
  C: {
    // Coalesced — gradient sky→emerald conveys "merged from both"
    label: "L|R",
    chip:
      "bg-gradient-to-r from-sky-200/80 to-emerald-200/80 text-slate-900 " +
      "dark:from-sky-900/50 dark:to-emerald-900/50 dark:text-slate-100 " +
      "ring-1 ring-slate-300/60 dark:ring-slate-700/40",
    stripe: "bg-gradient-to-b from-sky-400 to-emerald-400 dark:from-sky-500 dark:to-emerald-500",
    row: "bg-gradient-to-r from-sky-50/40 to-emerald-50/40 dark:from-sky-950/20 dark:to-emerald-950/20",
    sub: "text-slate-700/70 dark:text-slate-300/70",
  },
};

export function ResultColumnsPanel({
  value, onChange, leftCols, rightCols, leftRows, rightRows, keys, rule, suffixes, kind,
}: Props) {
  const cols = useMemo(
    () => deriveOutputColumns(leftCols, rightCols, leftRows, rightRows, keys, rule, suffixes, kind),
    [leftCols, rightCols, leftRows, rightRows, keys, rule, suffixes, kind],
  );

  const excluded = useMemo(() => new Set(value.excluded ?? []), [value.excluded]);
  const renames = value.renames ?? {};

  // Compute effective output names + duplicate detection on the included subset.
  const { effective, dupNames, blankNames } = useMemo(() => {
    const eff = new Map<string, { final: string; col: OutputCol }>();
    const seen = new Map<string, number>();
    const blanks = new Set<string>();
    for (const c of cols) {
      if (excluded.has(c.provId)) continue;
      const renamed = renames[c.provId];
      const final = renamed != null ? renamed : c.defaultName;
      if (renamed != null && renamed.trim() === "") {
        blanks.add(c.provId);
      }
      eff.set(c.provId, { final, col: c });
      seen.set(final, (seen.get(final) ?? 0) + 1);
    }
    const dups = new Set<string>();
    for (const [provId, { final }] of eff) {
      if ((seen.get(final) ?? 0) > 1) dups.add(provId);
    }
    return { effective: eff, dupNames: dups, blankNames: blanks };
  }, [cols, excluded, renames]);

  const includedCount = effective.size;
  const totalCount = cols.length;

  if (cols.length === 0) {
    return (
      <div className="rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
        Result columns appear here once both inputs are connected and sampled.
      </div>
    );
  }

  const setIncluded = (provId: string, included: boolean) => {
    const nextExcl = new Set(excluded);
    if (included) nextExcl.delete(provId);
    else nextExcl.add(provId);
    onChange({ ...value, excluded: Array.from(nextExcl) });
  };

  const setRename = (provId: string, defaultName: string, raw: string) => {
    const next = { ...renames };
    if (raw === "" || raw === defaultName) {
      delete next[provId];
    } else {
      next[provId] = raw;
    }
    onChange({ ...value, renames: next });
  };

  const hasDuplicates = dupNames.size > 0;
  const hasBlanks = blankNames.size > 0;

  return (
    <div className="rounded-md border border-border/60 bg-card/30 px-3 py-2 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">
          📋 Result columns
        </p>
        <span className="text-[10px] text-muted-foreground tabular-nums">
          {includedCount} of {totalCount} included
        </span>
      </div>

      {(hasDuplicates || hasBlanks) && (
        <div className="rounded-md border border-rose-300/60 dark:border-rose-700/50 bg-rose-50/60 dark:bg-rose-950/20 px-2.5 py-1.5 text-[11px] text-rose-800 dark:text-rose-200 leading-snug">
          {hasDuplicates && <p>⚠ Two columns share the same name. Rename one to resolve.</p>}
          {hasBlanks && <p>⚠ A column has a blank name. Restore or rename it.</p>}
        </div>
      )}

      <ul className="space-y-1">
        {cols.map((c) => {
          const isIncluded = !excluded.has(c.provId);
          const renamed = renames[c.provId];
          const finalName = renamed != null ? renamed : c.defaultName;
          const isDup = isIncluded && dupNames.has(c.provId);
          const isBlank = isIncluded && blankNames.has(c.provId);
          const showSourceHint = c.source !== finalName;
          const style = SIDE_STYLE[c.side];

          return (
            <li
              key={c.provId}
              className={[
                "relative flex items-center gap-2 pl-3 pr-2 py-1 rounded-md transition-colors",
                isIncluded ? style.row : "opacity-50 bg-muted/20",
                isDup || isBlank ? "ring-1 ring-rose-400/70 dark:ring-rose-600/50" : "",
              ].join(" ")}
            >
              <span
                className={[
                  "absolute left-0 top-1 bottom-1 w-[3px] rounded-r-sm",
                  isIncluded ? style.stripe : "bg-muted-foreground/30",
                ].join(" ")}
                aria-hidden="true"
              />

              <span
                className={[
                  "shrink-0 inline-flex items-center justify-center min-w-[26px] h-[20px] px-1 rounded text-[10px] font-semibold tabular-nums",
                  style.chip,
                ].join(" ")}
                title={c.side === "C" ? "Coalesced from left and right" : c.side === "L" ? "From left input" : "From right input"}
              >
                {style.label}
              </span>

              <input
                type="checkbox"
                checked={isIncluded}
                onChange={(e) => setIncluded(c.provId, e.target.checked)}
                aria-label={`Include ${finalName}`}
                className="shrink-0 h-3.5 w-3.5 cursor-pointer accent-foreground"
              />

              <input
                type="text"
                value={finalName}
                onChange={(e) => setRename(c.provId, c.defaultName, e.target.value)}
                disabled={!isIncluded}
                spellCheck={false}
                aria-label={`Output name for ${c.source}`}
                className={[
                  "flex-1 min-w-0 bg-transparent text-[12px] font-mono px-1 py-0.5 rounded",
                  "focus:outline-none focus:ring-1 focus:ring-ring/40",
                  isDup || isBlank ? "text-rose-700 dark:text-rose-300" : "",
                  renamed != null && renamed !== c.defaultName ? "italic" : "",
                ].join(" ")}
                placeholder={c.defaultName}
              />

              <span
                className={[
                  "shrink-0 text-[10px] uppercase tracking-wider tabular-nums",
                  style.sub,
                ].join(" ")}
                title="Sniffed type"
              >
                {c.type}
              </span>

              {showSourceHint && (
                <span
                  className={[
                    "shrink-0 text-[10px] font-mono whitespace-nowrap max-w-[120px] truncate",
                    style.sub,
                  ].join(" ")}
                  title={`Source: ${c.source} (${c.side === "C" ? "both sides" : c.side === "L" ? "left" : "right"})`}
                >
                  ← {c.source}
                </span>
              )}

              {(isDup || isBlank) && (
                <span
                  className="shrink-0 text-rose-600 dark:text-rose-400 text-[12px]"
                  title={isDup ? "Duplicate name" : "Blank name"}
                  aria-label={isDup ? "Duplicate name" : "Blank name"}
                >
                  ✕
                </span>
              )}
            </li>
          );
        })}
      </ul>

      <p className="text-[10px] text-muted-foreground/70 leading-snug pt-0.5">
        Uncheck to drop a column. Click the name to rename. Provenance
        is keyed on the source column, so collision-rule changes
        don&apos;t strand your edits.
      </p>
    </div>
  );
}

"use client";

/**
 * JoinKeysBuilder — the rich keys-array editor.
 *
 *   🪄 Suggested:
 *   [accept] customer_id ↔ customer_id   (98% match)
 *
 *   Active:
 *   ┌──────────────┬────┬──────────────┬────────┬──┐
 *   │ left.country │ =  │ right.iso2   │ ▰▰▰▰▱ │✕│
 *   │ str          │    │ str          │  72%   │  │
 *   └──────────────┴────┴──────────────┴────────┴──┘
 *   ⚠ amber match — type-compatible but only 72% sample overlap.
 *
 * Replaces the default array-renderer for the `keys` param when the
 * manifest declares `widget: "join_keys_builder"`.
 */
import { useMemo } from "react";
import {
  matchQuality,
  qualityBucket,
  suggestKeys,
  combinedMatchQuality,
  type RowSample,
  type KeySuggestion,
} from "./match-quality";

export interface JoinKey {
  left: string;
  /** Right column. For `op = "between"`, this is the LOW bound; the
   *  HIGH bound lives in `rightHigh`. */
  right: string;
  op?: "=" | "≈" | "<" | "<=" | ">" | ">=" | "between";
  /** Only used when `op = "between"`: the upper-bound right column.
   *  Compiled to `left BETWEEN right AND rightHigh`. */
  rightHigh?: string;
}

interface Props {
  value: JoinKey[];
  onChange: (next: JoinKey[]) => void;
  leftCols: string[];
  rightCols: string[];
  leftRows: RowSample[];
  rightRows: RowSample[];
  loading?: boolean;
}

const OPS: Array<{ id: NonNullable<JoinKey["op"]>; label: string; title?: string }> = [
  { id: "=",  label: "=",  title: "Exact equality" },
  { id: "≈",  label: "≈",  title: "Fuzzy match — case-insensitive, trimmed (LOWER(TRIM(...)))" },
  { id: "<",  label: "<" },
  { id: "<=", label: "≤" },
  { id: ">",  label: ">" },
  { id: ">=", label: "≥" },
  { id: "between", label: "between", title: "left BETWEEN right_low AND right_high (range/temporal join)" },
];

const BUCKET_BAR_CLASS: Record<string, string> = {
  green:   "text-emerald-600 dark:text-emerald-300",
  amber:   "text-amber-600 dark:text-amber-300",
  red:     "text-rose-600 dark:text-rose-300",
  unknown: "text-muted-foreground/60",
};

const BUCKET_HINT_CLASS: Record<string, string> = {
  green:   "",
  amber:   "text-amber-700 dark:text-amber-300",
  red:     "text-rose-700 dark:text-rose-300",
  unknown: "text-muted-foreground/70",
};

function _qualityBar(q: number | null): string {
  if (q == null) return "▱▱▱▱▱";
  const filled = Math.round(q * 5);
  return "▰".repeat(filled) + "▱".repeat(5 - filled);
}

function _hintForKey(left: string, right: string, q: number | null): string {
  const b = qualityBucket(q);
  if (b === "unknown") {
    return "Sampling rows — match quality will compute when sample loads.";
  }
  const pct = Math.round((q ?? 0) * 100);
  if (b === "green") {
    return `${pct}% sample overlap — looks like a clean key.`;
  }
  if (b === "amber") {
    return `${pct}% sample overlap. Some left rows have no match on the right; the join will produce NULLs (left/full) or drop them (inner). [show unmatched] in the live grid below.`;
  }
  return `${pct}% sample overlap — likely the wrong column on one side, or a type mismatch (try casting first).`;
}

export function JoinKeysBuilder({
  value, onChange, leftCols, rightCols, leftRows, rightRows, loading,
}: Props) {
  const keys = value ?? [];

  const suggestions = useMemo<KeySuggestion[]>(
    () => suggestKeys(leftRows, rightRows, leftCols, rightCols, keys),
    [leftRows, rightRows, leftCols, rightCols, keys],
  );

  // Per-key match quality, recomputed when keys or samples change.
  // The match-quality function is op-aware: `=` uses raw distinct, `≈`
  // fuzzy-normalises strings before intersection. Range/between ops
  // don't have a meaningful set-overlap signal — bucket reads "unknown".
  const qualities = useMemo(
    () =>
      keys.map((k) => {
        if (!k.left || !k.right) return null;
        const op = k.op ?? "=";
        if (op === "=" || op === "≈") {
          return matchQuality(leftRows, rightRows, k.left, k.right, op);
        }
        return null;
      }),
    [keys, leftRows, rightRows],
  );

  // Combined match-% across all equality keys (the AND tuple). When
  // any key is amber/red individually but the *combined* tuple is
  // worse, we surface that headline because the join's actual filter
  // is the combined predicate. Only meaningful with ≥2 equality keys.
  const eqKeyCount = keys.filter(
    (k) => (k.op ?? "=") === "=" && k.left && k.right,
  ).length;
  const combined = useMemo(
    () => (eqKeyCount >= 2 ? combinedMatchQuality(leftRows, rightRows, keys) : null),
    [eqKeyCount, leftRows, rightRows, keys],
  );

  const acceptSuggestion = (s: KeySuggestion) => {
    onChange([...keys, { left: s.left, right: s.right, op: "=" }]);
  };
  const updateKey = (idx: number, patch: Partial<JoinKey>) => {
    const next = keys.slice();
    next[idx] = { ...next[idx], ...patch };
    // Switching INTO `between`: ensure rightHigh exists. Switching OUT:
    // drop it so saved doc stays clean.
    if (patch.op != null) {
      if (patch.op === "between" && next[idx].rightHigh == null) {
        next[idx].rightHigh = "";
      } else if (patch.op !== "between" && next[idx].rightHigh != null) {
        delete next[idx].rightHigh;
      }
    }
    onChange(next);
  };
  const removeKey = (idx: number) => {
    onChange(keys.filter((_, i) => i !== idx));
  };
  const addKey = () => {
    onChange([...keys, { left: "", right: "", op: "=" }]);
  };

  // Combined match-% headline for composite keys. Surfaces the fact
  // that, e.g., country=country @ 95% AND city=city @ 95% can still
  // produce only 50% combined-tuple overlap.
  const combinedBucket = qualityBucket(combined);
  const combinedPct = combined != null ? Math.round(combined * 100) : null;

  return (
    <div className="space-y-2">
      {combined != null && combinedPct != null && (
        <div
          className={
            "text-[10px] flex items-center gap-1.5 px-2 py-1 rounded-md " +
            (combinedBucket === "green"
              ? "bg-emerald-50/60 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300"
              : combinedBucket === "amber"
              ? "bg-amber-50/60 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300"
              : "bg-rose-50/60 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300")
          }
          title="Combined-tuple sample overlap across all equality keys (AND). Differs from per-key %s when the columns are individually plausible but their combination isn't."
        >
          <span className="font-mono">{_qualityBar(combined)}</span>
          <span>
            <strong>{combinedPct}%</strong> combined ({eqKeyCount}-key tuple) sample overlap
          </span>
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="rounded-md border border-emerald-300/40 dark:border-emerald-700/40 bg-emerald-50/40 dark:bg-emerald-950/20 px-2.5 py-1.5">
          <p className="text-[10px] uppercase tracking-widest text-emerald-700 dark:text-emerald-300 mb-1">
            🪄 Suggested keys
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {suggestions.map((s, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => acceptSuggestion(s)}
                  title={s.reason}
                  className="text-[11px] px-2 py-0.5 rounded-md border border-emerald-400/60 bg-white/70 dark:bg-emerald-900/30 hover:bg-emerald-100 dark:hover:bg-emerald-800/50 font-mono"
                >
                  ➕ <span className="text-foreground/90">{s.left}</span>
                  <span className="mx-1 opacity-60">↔</span>
                  <span className="text-foreground/90">{s.right}</span>
                  <span className="ml-1.5 opacity-70">({Math.round(s.matchPct * 100)}%)</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Active keys */}
      <div className="space-y-1.5">
        {keys.map((k, idx) => {
          const q = qualities[idx];
          const bucket = qualityBucket(q);
          const hint = _hintForKey(k.left, k.right, q);
          return (
            <div key={idx} className="space-y-0.5">
              <div className="flex items-center gap-1.5">
                <select
                  value={k.left}
                  onChange={(e) => updateKey(idx, { left: e.target.value })}
                  className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-[12px] min-w-0"
                  aria-label={`Key ${idx + 1} left column`}
                >
                  <option value="">— left col —</option>
                  {leftCols.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
                <select
                  value={k.op ?? "="}
                  onChange={(e) =>
                    updateKey(idx, { op: e.target.value as JoinKey["op"] })
                  }
                  className="rounded-md border border-input bg-background px-1.5 py-1 text-[12px] font-mono"
                  aria-label={`Key ${idx + 1} operator`}
                >
                  {OPS.map((op) => (
                    <option key={op.id} value={op.id}>{op.label}</option>
                  ))}
                </select>
                <select
                  value={k.right}
                  onChange={(e) => updateKey(idx, { right: e.target.value })}
                  className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-[12px] min-w-0"
                  aria-label={
                    k.op === "between"
                      ? `Key ${idx + 1} right low bound`
                      : `Key ${idx + 1} right column`
                  }
                >
                  <option value="">
                    {k.op === "between" ? "— low —" : "— right col —"}
                  </option>
                  {rightCols.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
                {k.op === "between" && (
                  <>
                    <span className="text-[11px] text-muted-foreground select-none">and</span>
                    <select
                      value={k.rightHigh ?? ""}
                      onChange={(e) =>
                        updateKey(idx, { rightHigh: e.target.value })
                      }
                      className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-[12px] min-w-0"
                      aria-label={`Key ${idx + 1} right high bound`}
                    >
                      <option value="">— high —</option>
                      {rightCols.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </>
                )}
                <span
                  className={`font-mono text-[12px] tracking-tight ${BUCKET_BAR_CLASS[bucket]}`}
                  aria-label={hint}
                  title={hint}
                >
                  {_qualityBar(q)}
                </span>
                <button
                  type="button"
                  onClick={() => removeKey(idx)}
                  aria-label={`Remove key ${idx + 1}`}
                  className="text-muted-foreground hover:text-destructive text-sm leading-none px-1"
                >
                  ✕
                </button>
              </div>
              {(bucket === "amber" || bucket === "red") && k.left && k.right && (
                <p className={`text-[10px] leading-snug pl-1 ${BUCKET_HINT_CLASS[bucket]}`}>
                  ⚠ {hint}
                </p>
              )}
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={addKey}
        className="text-[11px] text-muted-foreground hover:text-foreground"
      >
        ➕ Add key
      </button>

      {keys.length === 0 && !loading && suggestions.length === 0 && (
        <p className="text-[11px] text-muted-foreground italic">
          Pick at least one key column pair on each side. The keys-builder
          will surface suggestions and a per-key match-quality bar as the
          live grid samples load.
        </p>
      )}
    </div>
  );
}

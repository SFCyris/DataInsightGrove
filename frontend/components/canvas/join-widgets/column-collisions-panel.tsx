"use client";

/**
 * ColumnCollisionsPanel — surfaces columns that exist on BOTH sides
 * (post-key-collapse) so the user can choose how each is resolved
 * inline. Renders ONLY when collisions exist — no panel, no noise
 * when the schemas are clean.
 *
 * The key UX point: never resolve collisions silently. Users who
 * inherited a join with `name` on both sides should see exactly what
 * happened (suffixed to `name_left` / `name_right`, by default) and
 * be able to override per-column without leaving the panel.
 *
 * The default rule lives on `value.rule`; per-column overrides stash
 * on `value.overrides` (a map from column name → rule). The widget
 * surfaces both knobs.
 */
type CollisionRule = "keep_both" | "keep_left" | "keep_right" | "coalesce";

interface ColumnCollisionsValue {
  rule: CollisionRule;
  suffixes: [string, string];
  overrides?: Record<string, CollisionRule>;
}

interface Props {
  value: ColumnCollisionsValue;
  onChange: (next: ColumnCollisionsValue) => void;
  leftCols: string[];
  rightCols: string[];
  /** Equality-key columns from the left side; we exclude these from
   *  the collision list since the equality-key columns get collapsed
   *  to a single output by the SQL builder. */
  excludeLeftCols: ReadonlySet<string>;
}

const RULE_LABEL: Record<CollisionRule, { emoji: string; label: string; help: string }> = {
  keep_both:  { emoji: "⊕", label: "keep both",  help: "Both columns survive with suffixes." },
  keep_left:  { emoji: "⊖", label: "keep left",  help: "Drop the right side's copy." },
  keep_right: { emoji: "⊕", label: "keep right", help: "Drop the left side's copy." },
  coalesce:   { emoji: "⊕", label: "coalesce",   help: "COALESCE(left, right) — left wins, right fills NULLs." },
};

export function ColumnCollisionsPanel({
  value, onChange, leftCols, rightCols, excludeLeftCols,
}: Props) {
  const collisions = leftCols.filter(
    (c) => rightCols.includes(c) && !excludeLeftCols.has(c),
  );

  if (collisions.length === 0) return null;

  const ruleFor = (col: string): CollisionRule =>
    value.overrides?.[col] ?? value.rule;

  const setRule = (col: string, rule: CollisionRule) => {
    const next = { ...value, overrides: { ...(value.overrides ?? {}), [col]: rule } };
    // Drop the override when it matches the default — keeps the doc clean.
    if (rule === value.rule && next.overrides) {
      const { [col]: _drop, ...rest } = next.overrides;
      next.overrides = rest;
    }
    onChange(next);
  };

  return (
    <div className="rounded-md border border-amber-300/40 dark:border-amber-700/40 bg-amber-50/30 dark:bg-amber-950/15 px-3 py-2 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[10px] uppercase tracking-widest text-amber-700 dark:text-amber-300">
          ⚠ Column collisions
        </p>
        <span className="text-[10px] text-muted-foreground">
          {collisions.length} column{collisions.length === 1 ? "" : "s"} on both sides
        </span>
      </div>
      <p className="text-[11px] text-amber-900/80 dark:text-amber-100/80 leading-snug">
        These columns exist on both inputs (and aren&apos;t the join key). Pick a per-column
        rule, or leave them on the default (<strong>{RULE_LABEL[value.rule].label}</strong>).
      </p>

      <div className="space-y-1">
        {collisions.map((col) => {
          const rule = ruleFor(col);
          const isOverridden = value.overrides?.[col] != null;
          return (
            <div key={col} className="flex items-center gap-2 text-[12px]">
              <span className="font-mono flex-1 truncate" title={col}>{col}</span>
              <select
                value={rule}
                onChange={(e) => setRule(col, e.target.value as CollisionRule)}
                className="rounded-md border border-input bg-background px-1.5 py-0.5 text-[11px]"
                aria-label={`Resolution for ${col}`}
              >
                {(Object.keys(RULE_LABEL) as CollisionRule[]).map((r) => (
                  <option key={r} value={r}>
                    {RULE_LABEL[r].emoji} {RULE_LABEL[r].label}
                  </option>
                ))}
              </select>
              {isOverridden && (
                <span
                  title="Per-column override (differs from the default rule above)"
                  className="text-[10px] text-amber-700 dark:text-amber-300"
                >
                  ◉
                </span>
              )}
              {rule === "keep_both" && (
                <span className="text-[10px] text-muted-foreground font-mono whitespace-nowrap">
                  → <span>{col}{value.suffixes[0]}</span>{" / "}<span>{col}{value.suffixes[1]}</span>
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Suffix editors — visible when the default OR any override is keep_both */}
      {(value.rule === "keep_both" ||
        Object.values(value.overrides ?? {}).includes("keep_both")) && (
        <div className="grid grid-cols-2 gap-2 pt-1.5 border-t border-amber-300/30 dark:border-amber-700/30">
          <label className="text-[11px] flex items-center gap-1.5">
            Left suffix
            <input
              type="text"
              value={value.suffixes[0]}
              onChange={(e) =>
                onChange({ ...value, suffixes: [e.target.value, value.suffixes[1]] })
              }
              className="flex-1 rounded-md border border-input bg-background px-1.5 py-0.5 text-[11px] font-mono"
            />
          </label>
          <label className="text-[11px] flex items-center gap-1.5">
            Right suffix
            <input
              type="text"
              value={value.suffixes[1]}
              onChange={(e) =>
                onChange({ ...value, suffixes: [value.suffixes[0], e.target.value] })
              }
              className="flex-1 rounded-md border border-input bg-background px-1.5 py-0.5 text-[11px] font-mono"
            />
          </label>
        </div>
      )}
    </div>
  );
}

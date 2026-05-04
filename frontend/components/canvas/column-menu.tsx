"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { api, type TypeDescriptor } from "@/lib/api/client";

export type ColumnAction =
  | { kind: "filter_eq"; column: string; value: unknown }
  | { kind: "filter_neq"; column: string; value: unknown }
  | { kind: "filter_isnull"; column: string }
  | { kind: "filter_notnull"; column: string }
  | { kind: "sort"; column: string; direction: "asc" | "desc" }
  | { kind: "cast"; column: string; targetType: string }
  | { kind: "rename"; column: string; to: string }
  | { kind: "drop"; column: string }
  | { kind: "group_by"; column: string }
  | { kind: "derive_from"; column: string }
  // Reorder = the new full left-to-right column order. Caller is responsible
  // for computing this from the current schema (drag handler does this; the
  // "Move column…" menu items below also compute it from `allColumns`).
  | { kind: "reorder"; order: string[] }
  // Insert a fresh column adjacent to `reference`. The editor adds an
  // `add_column` step with defaults (string type, NULL default) that the
  // user fine-tunes via the step's param form afterwards.
  | { kind: "insert_column"; position: "before" | "after"; reference: string }
  // Two-step composite: `pack_struct` (build a struct from N source
  // columns) followed by `cast_type` on that new column. Used by the
  // spatial-pair suggestions to take e.g. (LATITUDE, LONGITUDE) → a
  // single `geographic` column in one click. The dispatcher inserts both
  // steps in order and focuses the cast so the user can rename / tweak.
  | {
      kind: "pack_then_cast";
      outputColumn: string;
      fields: Array<{ fieldName: string; sourceColumn: string }>;
      targetType: string;
    }
  // Trace this column's lineage back to its dataset roots. The editor
  // opens the <LineagePanel /> drawer scoped to the focused node + column.
  | { kind: "trace_lineage"; column: string };

// Conservative fallback when the /types endpoint hasn't loaded (or the user
// is offline). These mirror the IDs in backend/dig/engine/meta_types.py.
const FALLBACK_TYPES: TypeDescriptor[] = [
  { id: "string",      label: "🅰️ string",      base: "string",  description: "Text" },
  { id: "integer",     label: "🔢 integer",     base: "integer", description: "Whole numbers" },
  { id: "double",      label: "🔢 double",      base: "double",  description: "Decimal numbers" },
  { id: "boolean",     label: "☑️ boolean",     base: "boolean", description: "True / false" },
  { id: "date",        label: "📅 date",        base: "date",    description: "Calendar date" },
  { id: "datetime",    label: "📅 datetime",    base: "datetime",description: "Date + time" },
];

interface Props {
  columnName: string;
  columnType?: string;
  /** Resolved logical type id (e.g. "url", "integer"). Used to mark the
   *  current type in the Cast list with a checkmark. */
  columnLogicalType?: string;
  /** Sorted candidate list from the column profile. Element [0] is the
   *  current pick — we surface elements [1..] as the smart-picks row at
   *  the top of the Cast section. */
  castCandidates?: Array<{ type: string; score: number; reason: string }>;
  /** Full column list for the focused step (left-to-right). Required to
   * build a complete `reorder` action — the move-column menu items here
   * compute the new order from this list. */
  allColumns?: string[];
  /** Auto-expand a section on mount. Used by the alternates badge to
   *  deep-link straight to the Cast pane. */
  initialOpen?: "cast";
  position: { x: number; y: number };
  onClose: () => void;
  onAction: (action: ColumnAction) => void;
}

export function ColumnMenu({
  columnName, columnType, columnLogicalType, castCandidates,
  allColumns, initialOpen, position, onClose, onAction,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [castOpen, setCastOpen] = useState(initialOpen === "cast");
  // "Show all types" expansion inside the Cast pane. Default closed —
  // smart picks first; the full catalog is one click away.
  const [castShowAll, setCastShowAll] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState(columnName);
  const [sortOpen, setSortOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveMode, setMoveMode] = useState<"before" | "after" | null>(null);

  // Lazy-load the type catalog only when the Cast section opens. Keeps the
  // menu's first-paint instant and avoids a 304 round-trip per right-click.
  const typesQ = useQuery({
    queryKey: ["dig", "types"],
    queryFn: () => api.listTypes(),
    enabled: castOpen,
    staleTime: 5 * 60_000,
  });
  const allTypes: TypeDescriptor[] = typesQ.data ?? FALLBACK_TYPES;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [onClose]);

  const fire = (a: ColumnAction) => {
    onAction(a);
    onClose();
  };

  // Position with viewport clamping
  const w = 240;
  const h = 380;
  const x = Math.min(position.x, window.innerWidth - w - 8);
  const y = Math.min(position.y, window.innerHeight - h - 8);

  return (
    <AnimatePresence>
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: -4, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 360, damping: 28 }}
        style={{ position: "fixed", left: x, top: y, width: w }}
        // font-sans is explicit on the popover root so menu items / type
        // labels never inherit the grid table's font-mono — the menu lives
        // in the same React subtree as LiveGrid, so without this the mono
        // can leak into "Cast to → double" and similar labels.
        className="z-50 rounded-lg border border-border bg-popover text-popover-foreground shadow-2xl py-1 text-sm font-sans"
      >
        <header className="px-3 py-2 border-b border-border/60 flex items-center gap-2 text-xs">
          <span className="text-muted-foreground uppercase tracking-wider">Column</span>
          <span className="font-medium truncate flex-1" title={columnName}>{columnName}</span>
          {columnType && (
            <span className="text-[10px] text-muted-foreground">{columnType}</span>
          )}
        </header>

        <Item
          label="🔍 Filter rows where this is NULL"
          onClick={() => fire({ kind: "filter_isnull", column: columnName })}
        />
        <Item
          label="🔍 Filter rows where this is NOT NULL"
          onClick={() => fire({ kind: "filter_notnull", column: columnName })}
        />
        <Item
          label="🔗 Trace lineage…"
          onClick={() => fire({ kind: "trace_lineage", column: columnName })}
        />

        <Sep />
        <Toggle label="↕️ Sort by this column" open={sortOpen} onToggle={() => setSortOpen((v) => !v)} />
        {sortOpen && (
          <div className="px-2 pb-1.5">
            <Sub
              label="ASC ↑"
              onClick={() => fire({ kind: "sort", column: columnName, direction: "asc" })}
            />
            <Sub
              label="DESC ↓"
              onClick={() => fire({ kind: "sort", column: columnName, direction: "desc" })}
            />
          </div>
        )}

        <Sep />
        <Toggle label="🔄 Cast to…" open={castOpen} onToggle={() => setCastOpen((v) => !v)} />
        {castOpen && (
          <CastSection
            currentType={columnLogicalType}
            candidates={castCandidates ?? []}
            allTypes={allTypes}
            showAll={castShowAll}
            onToggleShowAll={() => setCastShowAll((v) => !v)}
            onCast={(t) => fire({ kind: "cast", column: columnName, targetType: t })}
          />
        )}

        <Sep />
        <Toggle label="✏️ Rename column" open={renameOpen} onToggle={() => setRenameOpen((v) => !v)} />
        {renameOpen && (
          <div className="px-2 pb-2 flex gap-1.5">
            <input
              type="text"
              autoFocus
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && renameValue.trim() && renameValue !== columnName) {
                  fire({ kind: "rename", column: columnName, to: renameValue.trim() });
                }
              }}
              className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
            <button
              type="button"
              disabled={!renameValue.trim() || renameValue === columnName}
              onClick={() =>
                fire({ kind: "rename", column: columnName, to: renameValue.trim() })
              }
              className="text-xs px-2 rounded-md bg-foreground text-background disabled:opacity-40"
            >
              ↵
            </button>
          </div>
        )}

        <Item
          label="✂️ Drop column"
          onClick={() => fire({ kind: "drop", column: columnName })}
        />

        {allColumns && allColumns.length > 1 && (
          <>
            <Sep />
            <Toggle
              label="↔️ Move column…"
              open={moveOpen}
              onToggle={() => {
                setMoveOpen((v) => !v);
                setMoveMode(null);
              }}
            />
            {moveOpen && (
              <div className="px-2 pb-2 space-y-1">
                <div className="grid grid-cols-2 gap-0.5">
                  <Sub
                    label="⏮ To start"
                    onClick={() =>
                      fire({ kind: "reorder", order: moveColumn(allColumns, columnName, 0) })
                    }
                  />
                  <Sub
                    label="⏭ To end"
                    onClick={() =>
                      fire({ kind: "reorder", order: moveColumn(allColumns, columnName, allColumns.length - 1) })
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-0.5">
                  <Sub label="◀ Before…" onClick={() => setMoveMode("before")} />
                  <Sub label="After… ▶" onClick={() => setMoveMode("after")} />
                </div>
                {moveMode && (
                  <div className="border border-border/60 rounded-md bg-muted/30 p-1.5 max-h-[180px] overflow-y-auto">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground px-1 pb-1">
                      Move {moveMode}…
                    </p>
                    {allColumns
                      .filter((c) => c !== columnName)
                      .map((c) => (
                        <button
                          key={c}
                          type="button"
                          onClick={() =>
                            fire({
                              kind: "reorder",
                              order: moveColumnRelative(allColumns, columnName, c, moveMode),
                            })
                          }
                          className="w-full text-left px-2 py-1 text-xs rounded hover:bg-muted truncate"
                          title={c}
                        >
                          {c}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <Sep />
        <Item
          label="🆕 Insert column before this"
          onClick={() => fire({ kind: "insert_column", position: "before", reference: columnName })}
        />
        <Item
          label="🆕 Insert column after this"
          onClick={() => fire({ kind: "insert_column", position: "after", reference: columnName })}
        />

        <Sep />
        <Item
          label="📊 Group by this column"
          onClick={() => fire({ kind: "group_by", column: columnName })}
        />
        <Item
          label="➕ Derive from this column"
          onClick={() => fire({ kind: "derive_from", column: columnName })}
        />
      </motion.div>
    </AnimatePresence>
  );
}

/**
 * Cast section UX: smart picks first, full catalog on demand.
 *
 * Layout (top to bottom):
 *   1. "Smart picks" row — alternate candidates from profiling, sorted by
 *      score, each with the detector's reason on hover. Skipped entirely
 *      when there's only the current type's candidate (i.e. nothing
 *      smarter to suggest).
 *   2. The current type, marked with a checkmark — explicit so the user
 *      always sees what they have now.
 *   3. "Show all types" toggle revealing the full /types catalog grouped
 *      visually by base physical type.
 *
 * Why progressive disclosure: 19+ types overflow the menu and force the
 * user to scan a wall of options. Surfacing the 1–3 most likely up front
 * matches the actual workflow ("the detector picked X but I want one of
 * the alternates it considered").
 */
function CastSection({
  currentType,
  candidates,
  allTypes,
  showAll,
  onToggleShowAll,
  onCast,
}: {
  currentType?: string;
  candidates: Array<{ type: string; score: number; reason: string; storage?: string | null }>;
  allTypes: TypeDescriptor[];
  showAll: boolean;
  onToggleShowAll: () => void;
  onCast: (typeId: string) => void;
}) {
  const byId: Record<string, TypeDescriptor> = {};
  for (const t of allTypes) byId[t.id] = t;

  // Smart picks = candidates other than the current one, score ≥ 0.50
  // already filtered server-side by ALTERNATE_MIN_SCORE.
  const smartPicks = candidates.filter(
    (c) => c.type !== currentType && c.score >= 0.5,
  );

  // Group by base physical type so the 19 entries cluster meaningfully
  // (numeric meta-types beside `double`, string meta-types beside `string`).
  // Order the bases by the natural reading sequence the cast manifest enum
  // uses — physical primitives first, meta-types tucked under their base.
  const BASE_ORDER = ["string", "integer", "double", "boolean", "date", "datetime"];
  const groupedByBase: Record<string, TypeDescriptor[]> = {};
  for (const t of allTypes) {
    (groupedByBase[t.base] ??= []).push(t);
  }
  // Sort within each base: the base type itself first (id === base), then
  // meta-types alphabetically by label.
  for (const list of Object.values(groupedByBase)) {
    list.sort((a, b) => {
      if (a.id === a.base && b.id !== b.base) return -1;
      if (b.id === b.base && a.id !== a.base) return 1;
      return a.label.localeCompare(b.label);
    });
  }
  const orderedBases = [
    ...BASE_ORDER.filter((b) => b in groupedByBase),
    ...Object.keys(groupedByBase).filter((b) => !BASE_ORDER.includes(b)),
  ];

  return (
    <div className="px-2 pb-1.5 space-y-1.5">
      {smartPicks.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground px-1 pb-1 flex items-center gap-1">
            <span aria-hidden>✨</span> Smart picks
          </p>
          <div className="space-y-0.5">
            {smartPicks.map((c) => {
              const td = byId[c.type];
              const label = td?.label ?? c.type;
              const pct = Math.round(c.score * 100);
              // Show the SQL storage when the detector chose something
              // other than the descriptor's default — that's where the
              // user's "what changes if I cast?" trade-off lives. e.g.
              // "scientific → VARCHAR" tells the user values won't fit DOUBLE.
              const storageOverride =
                c.storage && td && c.storage !== td.base.toUpperCase() && c.storage !== td.label.split(" ")[1]?.toUpperCase()
                  ? c.storage
                  : null;
              return (
                <button
                  key={c.type}
                  type="button"
                  onClick={() => onCast(c.type)}
                  title={`${c.reason}${c.storage ? ` (stored as ${c.storage})` : ""}`}
                  className="w-full text-left px-2 py-1 rounded hover:bg-muted text-xs flex items-center gap-2"
                >
                  <span className="flex-1 truncate">{label}</span>
                  {storageOverride && (
                    <span className="text-[10px] text-amber-600 dark:text-amber-400 font-mono" title={`Stored as ${storageOverride}`}>
                      → {storageOverride}
                    </span>
                  )}
                  <span className="text-[10px] text-muted-foreground tabular-nums">{pct}%</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {currentType && byId[currentType] && (
        <div className="flex items-center gap-2 px-2 py-1 rounded bg-muted/40 text-xs">
          <span className="text-emerald-600 dark:text-emerald-400" aria-hidden>✓</span>
          <span className="flex-1 truncate">{byId[currentType].label}</span>
          <span className="text-[10px] text-muted-foreground">current</span>
        </div>
      )}

      <button
        type="button"
        onClick={onToggleShowAll}
        aria-expanded={showAll}
        className="w-full text-left px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors flex items-center justify-between"
      >
        <span>{showAll ? "Hide full type list" : "Show all types"}</span>
        <span aria-hidden>{showAll ? "▴" : "▾"}</span>
      </button>

      {showAll && (
        <div className="max-h-[260px] overflow-y-auto border border-border/40 rounded-md p-1 bg-muted/20 space-y-1.5">
          {orderedBases.map((baseName) => (
            <div key={baseName}>
              <p className="text-[9px] uppercase tracking-wider text-muted-foreground/80 px-1 pb-0.5">
                {baseName}
              </p>
              <div className="grid grid-cols-2 gap-0.5">
                {groupedByBase[baseName].map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => onCast(t.id)}
                    title={t.description}
                    className={[
                      "text-left px-2 py-1 rounded text-xs truncate transition-colors",
                      t.id === currentType
                        ? "bg-emerald-100/60 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-100"
                        : "hover:bg-muted",
                    ].join(" ")}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Item({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-3 py-1.5 hover:bg-muted/60 transition-colors"
    >
      {label}
    </button>
  );
}

function Toggle({
  label, open, onToggle,
}: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="w-full text-left px-3 py-1.5 hover:bg-muted/60 transition-colors flex items-center justify-between"
    >
      <span>{label}</span>
      <span aria-hidden className="text-xs text-muted-foreground">{open ? "▴" : "▾"}</span>
    </button>
  );
}

function Sub({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left px-2 py-1 rounded hover:bg-muted text-xs"
    >
      {label}
    </button>
  );
}

function Sep() {
  return <div className="h-px bg-border/60 my-1" />;
}

/** Move `column` to the given absolute target position. Returns the new
 * full order. Clamps target to the valid range. No-op if column missing. */
function moveColumn(all: string[], column: string, target: number): string[] {
  const without = all.filter((c) => c !== column);
  if (!all.includes(column)) return [...all];
  const insertAt = Math.max(0, Math.min(target, without.length));
  const next = [...without];
  next.splice(insertAt, 0, column);
  return next;
}

/** Move `column` immediately before/after `reference`. */
function moveColumnRelative(
  all: string[],
  column: string,
  reference: string,
  mode: "before" | "after",
): string[] {
  const without = all.filter((c) => c !== column);
  let refIdx = without.indexOf(reference);
  if (refIdx < 0) return [...all];
  if (mode === "after") refIdx += 1;
  const next = [...without];
  next.splice(refIdx, 0, column);
  return next;
}

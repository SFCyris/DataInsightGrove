"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";

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
  | { kind: "insert_column"; position: "before" | "after"; reference: string };

const TYPES = ["string", "integer", "double", "boolean", "date", "datetime"] as const;

interface Props {
  columnName: string;
  columnType?: string;
  /** Full column list for the focused step (left-to-right). Required to
   * build a complete `reorder` action — the move-column menu items here
   * compute the new order from this list. */
  allColumns?: string[];
  position: { x: number; y: number };
  onClose: () => void;
  onAction: (action: ColumnAction) => void;
}

export function ColumnMenu({ columnName, columnType, allColumns, position, onClose, onAction }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [castOpen, setCastOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState(columnName);
  const [sortOpen, setSortOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveMode, setMoveMode] = useState<"before" | "after" | null>(null);

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
        className="z-50 rounded-lg border border-border bg-popover text-popover-foreground shadow-2xl py-1 text-sm"
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
          <div className="px-2 pb-1.5 grid grid-cols-2 gap-0.5">
            {TYPES.map((t) => (
              <Sub
                key={t}
                label={t}
                onClick={() => fire({ kind: "cast", column: columnName, targetType: t })}
              />
            ))}
          </div>
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

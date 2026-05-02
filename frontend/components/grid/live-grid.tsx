"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ColumnMenu, type ColumnAction } from "@/components/canvas/column-menu";
import { ProfileDrawer } from "@/components/grid/profile-drawer";
import { fmtInt } from "@/lib/format-number";
import { findIndexDuplicates, isValidTimezone } from "@/lib/meta-types";

const TYPE_EMOJI: Record<string, string> = {
  integer: "🔢", double: "🔢", string: "🅰️", date: "📅",
  datetime: "📅", boolean: "☑️", nested: "🧱",
  // Meta-types — same base storage but distinct visual identity so the
  // user can see at a glance that these are constraint-bearing columns.
  index: "🔑", timezone: "🌍",
};

interface Column {
  name: string;
  type: string;
}

interface Highlights {
  /** column name -> visual treatment as "newly added by current step" (green tint) */
  added?: Set<string>;
  /** columns renamed by the current step (yellow tint) */
  renamed?: Set<string>;
  /** column to softly emphasize (e.g. when the user hovers a hint) */
  hovered?: string | null;
}

interface Props {
  columns: Column[];
  rows: Array<Record<string, unknown>>;
  totalRows: number;
  sampleRows: number;
  loading?: boolean;
  elapsedMs?: number | null;
  onColumnAction: (action: ColumnAction) => void;
  /** Called when user clicks a cell value — for "filter to this value" quick action. */
  onCellQuickFilter?: (column: string, value: unknown, mode: "eq" | "neq") => void;
  emptyHint?: React.ReactNode;
  highlights?: Highlights;
  /** Per-column annotations (from the focused dataset, if any). */
  annotations?: Record<string, string>;
  /** Save callback for the drawer's annotation editor. */
  onSaveAnnotation?: (column: string, text: string) => Promise<void> | void;
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") {
    if (!isFinite(v)) return "—";
    if (Number.isInteger(v)) return fmtInt(v);
    // Locale-stable float formatting (was toLocaleString(undefined, ...) which
    // changed grouping separator between SSR and client locales).
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(v);
  }
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function shortType(t: string): string {
  if (!t) return "?";
  const m = t.toLowerCase();
  if (m.startsWith("int") || m === "bigint") return "int";
  if (m === "double" || m === "float" || m === "float32" || m === "float64") return "num";
  if (m === "varchar" || m === "string" || m === "utf8") return "str";
  if (m.startsWith("bool")) return "bool";
  if (m.startsWith("date") || m.startsWith("timestamp")) return "date";
  if (m.includes("decimal")) return "num";
  return m.split("(")[0];
}

function logicalType(t: string): string {
  const m = t.toLowerCase();
  // Meta-types are exposed as-is so the grid can branch on them.
  if (m === "index") return "index";
  if (m === "timezone") return "timezone";
  if (m.startsWith("int") || m === "bigint") return "integer";
  if (m === "double" || m === "float" || m === "float32" || m === "float64" || m.includes("decimal")) return "double";
  if (m.startsWith("bool")) return "boolean";
  if (m === "date") return "date";
  if (m.startsWith("timestamp") || m === "datetime") return "datetime";
  return "string";
}

export function LiveGrid({
  columns, rows, totalRows, sampleRows, loading = false, elapsedMs,
  onColumnAction, onCellQuickFilter, emptyHint, highlights,
  annotations, onSaveAnnotation,
}: Props) {
  const added = highlights?.added;
  const renamed = highlights?.renamed;
  const hovered = highlights?.hovered;
  // Onboarding tooltip on first column ⋯ (one-time per browser).
  const [showOnboard, setShowOnboard] = useState(false);
  const firstChevronRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (!localStorage.getItem("dig.tour.column_chevron") && columns.length > 0) {
        const t = setTimeout(() => setShowOnboard(true), 1200);
        return () => clearTimeout(t);
      }
    } catch {
      /* ignore */
    }
  }, [columns.length]);
  const dismissOnboard = useCallback(() => {
    setShowOnboard(false);
    try {
      localStorage.setItem("dig.tour.column_chevron", "1");
    } catch {
      /* ignore */
    }
  }, []);
  const [menu, setMenu] = useState<{ x: number; y: number; col: Column } | null>(null);
  const [hoveredCol, setHoveredCol] = useState<string | null>(null);
  const [profileFor, setProfileFor] = useState<Column | null>(null);
  // Drag-to-reorder state. dragCol = column being dragged; dragOver = column
  // currently under the cursor; dropEdge = whether to insert before/after.
  // We use HTML5 native DnD because (a) it's free, (b) it gives us the
  // correct cursor + ghost out of the box.
  const [dragCol, setDragCol] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<{ col: string; edge: "left" | "right" } | null>(null);

  const openMenu = useCallback((e: React.MouseEvent, col: Column) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setMenu({ x: rect.left, y: rect.bottom + 4, col });
  }, []);

  // Compute the current column-name list once per render — used by the
  // column menu (Move column → before/after picker) and by the drag drop
  // handler to construct the reorder action.
  const columnNames = useMemo(() => columns.map((c) => c.name), [columns]);

  // Per-column "invalid value" predicate, computed once per render. Two
  // meta-types contribute:
  //   - index:    duplicate values are invalid (precompute the dup set)
  //   - timezone: non-IANA strings are invalid (per-cell membership check)
  // For all other types the predicate is a constant `false` — zero cost.
  const cellInvalidByCol = useMemo(() => {
    const out: Record<string, (v: unknown) => boolean> = {};
    for (const c of columns) {
      const t = logicalType(c.type);
      if (t === "index") {
        const dupes = findIndexDuplicates(rows.map((r) => r[c.name]));
        out[c.name] = (v: unknown) => v !== null && v !== undefined && dupes.has(v);
      } else if (t === "timezone") {
        out[c.name] = (v: unknown) => v !== null && v !== undefined && !isValidTimezone(v);
      } else {
        out[c.name] = () => false;
      }
    }
    return out;
  }, [columns, rows]);

  const handleHeaderDrop = useCallback(
    (target: string, edge: "left" | "right") => {
      if (!dragCol || dragCol === target) {
        setDragCol(null);
        setDragOver(null);
        return;
      }
      const without = columnNames.filter((c) => c !== dragCol);
      let idx = without.indexOf(target);
      if (idx < 0) {
        setDragCol(null);
        setDragOver(null);
        return;
      }
      if (edge === "right") idx += 1;
      const next = [...without];
      next.splice(idx, 0, dragCol);
      onColumnAction({ kind: "reorder", order: next });
      setDragCol(null);
      setDragOver(null);
    },
    [dragCol, columnNames, onColumnAction],
  );

  // Cap rendered rows at 500 — plain <table> handles this comfortably
  // without virtualization. The status strip below shows total + the
  // "showing first N of M" hint when truncated.
  const RENDER_CAP = 500;
  const renderedRows = rows.length > RENDER_CAP ? rows.slice(0, RENDER_CAP) : rows;
  const previewCount = renderedRows.length;

  return (
    <div className="flex flex-col h-full min-h-0 relative">
      {/* Status strip */}
      <div className="px-3 py-1.5 border-b border-border bg-muted/20 flex items-center gap-3 text-xs tabular-nums shrink-0">
        <span className="flex items-center gap-1.5">
          <span aria-hidden>📊</span>
          <span className="font-medium text-foreground">
            {fmtInt(totalRows)}
          </span>
          <span className="text-muted-foreground">rows</span>
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">
          {columns.length} cols
        </span>
        {elapsedMs != null && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground">{elapsedMs} ms</span>
          </>
        )}
        <span className="flex-1" />
        {totalRows > previewCount && (
          <span className="text-[10px] text-muted-foreground">
            showing first {fmtInt(previewCount)} of {fmtInt(totalRows)}
          </span>
        )}
        <span className="text-[10px] px-2 py-0.5 rounded-full border border-amber-300/40 bg-amber-50/40 dark:bg-amber-900/10 text-amber-700 dark:text-amber-300">
          🦆 sample · {fmtInt(sampleRows)}
        </span>
        {loading && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-[10px] text-muted-foreground"
          >
            ⏳ recomputing…
          </motion.span>
        )}
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-auto relative">
        {columns.length === 0 || rows.length === 0 ? (
          <div className="absolute inset-0 grid place-items-center text-center text-sm text-muted-foreground">
            {emptyHint ?? (
              <div>
                <div className="text-5xl mb-2">🌱</div>
                <p>No data yet — add a dataset to begin.</p>
              </div>
            )}
          </div>
        ) : (
          <table
            className="w-full text-xs tabular-nums"
            role="grid"
            aria-rowcount={totalRows ?? rows.length}
            aria-colcount={columns.length}
          >
            <caption className="sr-only">
              Live grid · {columns.length} columns · {fmtInt(totalRows ?? rows.length)} rows.
              Sample of {previewCount} rows shown.
            </caption>
            <thead className="sticky top-0 z-10 bg-card/95 backdrop-blur">
              <tr>
                {columns.map((c, ci) => {
                  const isHover = hoveredCol === c.name;
                  const isAdded = added?.has(c.name);
                  const isRenamed = renamed?.has(c.name);
                  const isExternalHover = hovered === c.name;
                  const isDragging = dragCol === c.name;
                  const isDropTarget = dragOver?.col === c.name;
                  return (
                    <th
                      key={c.name}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.effectAllowed = "move";
                        // Some browsers refuse to start a drag without payload.
                        e.dataTransfer.setData("text/plain", c.name);
                        setDragCol(c.name);
                      }}
                      onDragEnd={() => {
                        setDragCol(null);
                        setDragOver(null);
                      }}
                      onDragOver={(e) => {
                        if (!dragCol || dragCol === c.name) return;
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                        // Choose the drop edge based on which half of the
                        // header the cursor is over — same gesture pattern as
                        // browser tab reordering.
                        const rect = e.currentTarget.getBoundingClientRect();
                        const edge: "left" | "right" =
                          e.clientX < rect.left + rect.width / 2 ? "left" : "right";
                        setDragOver((cur) =>
                          cur && cur.col === c.name && cur.edge === edge ? cur : { col: c.name, edge },
                        );
                      }}
                      onDragLeave={() => {
                        setDragOver((cur) => (cur && cur.col === c.name ? null : cur));
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        const edge = dragOver?.col === c.name ? dragOver.edge : "right";
                        handleHeaderDrop(c.name, edge);
                      }}
                      onMouseEnter={() => setHoveredCol(c.name)}
                      onMouseLeave={() => setHoveredCol((cur) => (cur === c.name ? null : cur))}
                      onContextMenu={(e) => {
                        e.preventDefault();
                        setMenu({ x: e.clientX, y: e.clientY, col: c });
                      }}
                      className={[
                        "text-left px-2 py-1.5 border-b whitespace-nowrap font-medium relative",
                        "cursor-grab active:cursor-grabbing select-none transition-colors",
                        isDragging ? "opacity-40" : "",
                        isAdded
                          ? "border-emerald-400/60 bg-emerald-50/60 dark:bg-emerald-900/20"
                          : isRenamed
                            ? "border-amber-400/60 bg-amber-50/60 dark:bg-amber-900/20"
                            : isExternalHover
                              ? "border-emerald-300/40 bg-emerald-50/40 dark:bg-emerald-900/15"
                              : isHover
                                // Same emerald tint as the column body so the
                                // whole column reads as one highlighted unit.
                                ? "border-emerald-300/40 bg-emerald-100/50 dark:bg-emerald-500/15"
                                : "border-border",
                      ].join(" ")}
                    >
                      {/* Drop indicator: vertical accent line on the chosen
                          edge of the hovered header during a drag. */}
                      {isDropTarget && (
                        <span
                          aria-hidden
                          className={[
                            "absolute top-0 bottom-0 w-0.5 bg-emerald-500 pointer-events-none",
                            dragOver?.edge === "left" ? "left-0" : "right-0",
                          ].join(" ")}
                        />
                      )}
                      <div className="flex items-center gap-1.5">
                        <span aria-hidden>{TYPE_EMOJI[logicalType(c.type)] ?? "❔"}</span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setProfileFor(c);
                          }}
                          className="truncate hover:underline underline-offset-2 text-left"
                          title={`Open profile for ${c.name}`}
                        >
                          {c.name}
                        </button>
                        {(() => {
                          // Inline data-quality badge: how many cells in
                          // this column are invalid? Reads from the same
                          // memo the cell renderer uses so it stays in
                          // perfect lockstep.
                          const t = logicalType(c.type);
                          if (t !== "index" && t !== "timezone") return null;
                          const predicate = cellInvalidByCol[c.name];
                          let bad = 0;
                          for (const r of renderedRows) {
                            if (predicate(r[c.name])) bad++;
                          }
                          if (bad === 0) return null;
                          return (
                            <span
                              className="ml-1 inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300 border border-rose-300/60"
                              title={t === "index"
                                ? `${bad} duplicate value(s) in this index column`
                                : `${bad} cell(s) are not valid IANA timezones`}
                            >
                              ⚠ {bad}
                            </span>
                          );
                        })()}
                        <span className="text-[10px] text-muted-foreground/70 ml-0.5">
                          {shortType(c.type)}
                        </span>
                        <button
                          ref={ci === 0 ? firstChevronRef : undefined}
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            dismissOnboard();
                            openMenu(e, c);
                          }}
                          aria-label={`Operations on ${c.name}`}
                          aria-haspopup="menu"
                          // Hit area = ≥24×24 (was p-0.5, ~12×16 — under WCAG
                          // target size). Always-on opacity bumped from 50→70
                          // so the chevron reads even before hover.
                          className={[
                            "ml-auto inline-flex items-center justify-center rounded h-6 w-6",
                            "text-muted-foreground hover:text-foreground hover:bg-muted transition-opacity",
                            isHover ? "opacity-100" : "opacity-70",
                          ].join(" ")}
                        >
                          ⋯
                        </button>
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody onMouseLeave={() => setHoveredCol(null)}>
              {/* No AnimatePresence here: it caused a 200×N cell-mount cycle
                  on every preview keystroke. Plain <tr> with hover bg is
                  fast + visually clean. */}
              {renderedRows.map((r, ri) => (
                <tr
                  key={ri}
                  className="hover:bg-muted/40"
                >
                    {columns.map((c) => {
                      const v = r[c.name];
                      const isAddedCell = added?.has(c.name);
                      const isRenamedCell = renamed?.has(c.name);
                      // Hover-highlight the WHOLE column when the user is over
                      // any cell in it (or the header). hoveredCol is set on
                      // both <th> and <td> mouseenter — see handlers below.
                      const isExternalHoverCell = hovered === c.name;
                      const isColHovered = hoveredCol === c.name;
                      // Meta-type validity check — duplicates for index
                      // columns, non-IANA strings for timezone columns.
                      const isCellInvalid = cellInvalidByCol[c.name](v);
                      const colLogicalType = logicalType(c.type);
                      return (
                        <td
                          key={c.name}
                          onMouseEnter={() => setHoveredCol(c.name)}
                          onClick={(e) => {
                            if ((e.metaKey || e.ctrlKey) && onCellQuickFilter) {
                              e.preventDefault();
                              onCellQuickFilter(c.name, v, e.altKey ? "neq" : "eq");
                            }
                          }}
                          title={
                            isCellInvalid
                              ? colLogicalType === "index"
                                ? `Duplicate value: ${String(v)} appears more than once in this index column`
                                : `Invalid IANA timezone: "${String(v)}" — try America/New_York, Europe/Berlin, UTC, …`
                              : onCellQuickFilter
                                ? "⌘+click to filter to this value · ⌘+alt+click to exclude"
                                : undefined
                          }
                          className={[
                            "px-2 py-1 border-b border-border/30 whitespace-nowrap max-w-[260px] truncate transition-colors",
                            colLogicalType === "integer" || colLogicalType === "double" || colLogicalType === "index"
                              ? "text-right"
                              : "",
                            v === null || v === undefined ? "text-muted-foreground/40 italic" : "",
                            // Invalid wins over EVERY other tint — it's a
                            // hard data-quality signal, not a transient
                            // editor cue.
                            isCellInvalid
                              ? "bg-rose-100 text-rose-900 dark:bg-rose-900/40 dark:text-rose-100 ring-1 ring-inset ring-rose-400/60"
                              : isAddedCell
                                ? "bg-emerald-50/40 dark:bg-emerald-900/15"
                                : isRenamedCell
                                  ? "bg-amber-50/40 dark:bg-amber-900/10"
                                  : isExternalHoverCell
                                    ? "bg-emerald-50/30 dark:bg-emerald-900/10"
                                    : isColHovered
                                      // Whole-column hover tint — sage-emerald,
                                      // designed to feel like a soft spotlight
                                      // without competing with the diff colors.
                                      ? "bg-emerald-100/40 dark:bg-emerald-500/10"
                                      : "",
                          ].join(" ")}
                        >
                          {fmt(v)}
                        </td>
                      );
                    })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {menu && (
        <ColumnMenu
          columnName={menu.col.name}
          columnType={shortType(menu.col.type)}
          allColumns={columnNames}
          position={{ x: menu.x, y: menu.y }}
          onClose={() => setMenu(null)}
          onAction={onColumnAction}
        />
      )}

      {/* First-time onboarding tooltip on the column ⋯ chevron */}
      <AnimatePresence>
        {showOnboard && firstChevronRef.current && (
          <OnboardingBubble target={firstChevronRef.current} onDismiss={dismissOnboard} />
        )}
      </AnimatePresence>

      {/* Column profile drawer */}
      <ProfileDrawer
        open={profileFor !== null}
        onClose={() => setProfileFor(null)}
        columnName={profileFor?.name ?? null}
        columnType={profileFor?.type}
        rows={rows}
        columns={columns}
        annotation={profileFor ? annotations?.[profileFor.name] : undefined}
        onSaveAnnotation={onSaveAnnotation}
      />
    </div>
  );
}

function OnboardingBubble({
  target, onDismiss,
}: { target: HTMLElement; onDismiss: () => void }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  useEffect(() => {
    const measure = () => {
      const r = target.getBoundingClientRect();
      setPos({ x: r.right + 8, y: r.top - 4 });
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [target]);
  if (!pos) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: -4, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      style={{
        position: "fixed",
        left: Math.min(pos.x, window.innerWidth - 280 - 8),
        top: Math.max(8, pos.y),
        width: 280,
      }}
      className="z-50 rounded-lg bg-foreground text-background shadow-2xl p-3 text-xs"
    >
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-base">👈</span>
        <div className="flex-1">
          <p className="font-medium">Click any <span className="font-mono">⋯</span> to act on a column</p>
          <p className="opacity-80 mt-1 leading-snug">
            Filter, sort, cast, rename, drop, group by, or derive — every action becomes a step in your pipeline.
          </p>
          <button
            type="button"
            onClick={onDismiss}
            className="mt-2 text-[11px] underline-offset-2 hover:underline opacity-80 hover:opacity-100"
          >
            Got it ✓
          </button>
        </div>
      </div>
    </motion.div>
  );
}

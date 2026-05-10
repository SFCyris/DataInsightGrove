"use client";

/**
 * Library toolbar — search + sort controls for the Pipelines and
 * Datasets library lists.
 *
 *   ┌─ 🔍 search…                Sort: 📝 Name  🆕 Added  ✏ Updated ↓
 *   │                            (active chip shows the direction arrow)
 *   └─ "12 of 48 pipelines"      (cardinality readout, only when filtered)
 *
 * Click a sort chip once → switches to that field with its sensible
 * default direction (alphabetical for name; newest-first for dates).
 * Click the *active* chip again → flips the arrow.
 *
 * State is persisted per-list via localStorage so the user's
 * preference survives page refreshes. Each library passes its own
 * `storageKey`.
 */
import { useEffect, useMemo, useState } from "react";

export type SortField = "name" | "createdAt" | "updatedAt";
export type SortDirection = "asc" | "desc";

export interface SortState {
  field: SortField;
  direction: SortDirection;
}

export interface LibraryView {
  query: string;
  setQuery: (s: string) => void;
  sort: SortState;
  /** Click handler — same field flips direction; new field resets to its
   *  per-field default ("asc" for name, "desc" for dates). */
  setSortField: (field: SortField) => void;
}

const DEFAULT_DIRECTION: Record<SortField, SortDirection> = {
  name: "asc",
  createdAt: "desc",
  updatedAt: "desc",
};

const FIELD_META: Record<SortField, { label: string; emoji: string; tooltip: string }> = {
  name:      { label: "Name",    emoji: "📝", tooltip: "Sort alphabetically by name" },
  createdAt: { label: "Added",   emoji: "🆕", tooltip: "Sort by date added" },
  updatedAt: { label: "Updated", emoji: "✏",  tooltip: "Sort by last edit time" },
};

export function useLibraryView(
  storageKey: string,
  defaultSort: SortState = { field: "updatedAt", direction: "desc" },
): LibraryView {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortState>(defaultSort);

  // Hydrate from localStorage once on mount. We don't sync query — it's
  // a per-session affordance, not a long-lived preference.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<SortState>;
      if (
        parsed.field
        && parsed.field in DEFAULT_DIRECTION
        && (parsed.direction === "asc" || parsed.direction === "desc")
      ) {
        setSort({ field: parsed.field, direction: parsed.direction });
      }
    } catch {
      // Corrupt entry — ignore.
    }
    // Run once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist on every change. Cheap; the JSON is two short strings.
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(sort));
    } catch {
      // localStorage full or unavailable (private mode) — ignore.
    }
  }, [storageKey, sort]);

  const setSortField = (field: SortField) => {
    setSort((cur) =>
      cur.field === field
        ? { ...cur, direction: cur.direction === "asc" ? "desc" : "asc" }
        : { field, direction: DEFAULT_DIRECTION[field] },
    );
  };

  return { query, setQuery, sort, setSortField };
}

/**
 * Apply a `LibraryView`'s search + sort to a list of items. Items must
 * have `name`, `createdAt`, `updatedAt` — both `Dataset` and
 * `PipelineSummary` shapes satisfy this.
 *
 * Search is a case-insensitive substring match against `name`. Empty
 * query bypasses the filter.
 */
export function filterAndSortLibrary<
  T extends { name: string; createdAt: string; updatedAt: string },
>(items: readonly T[], view: LibraryView): T[] {
  const q = view.query.trim().toLowerCase();
  const filtered = q
    ? items.filter((it) => (it.name || "").toLowerCase().includes(q))
    : items.slice();

  const { field, direction } = view.sort;
  const dir = direction === "asc" ? 1 : -1;
  filtered.sort((a, b) => {
    if (field === "name") {
      // Locale-aware so accented and uppercase names sort intuitively.
      return (a.name || "").localeCompare(b.name || "", undefined, {
        sensitivity: "base", numeric: true,
      }) * dir;
    }
    // Dates compare lexicographically as ISO-8601 strings — no parse cost.
    const av = a[field] || "";
    const bv = b[field] || "";
    return av < bv ? -1 * dir : av > bv ? 1 * dir : 0;
  });
  return filtered;
}

interface ToolbarProps {
  view: LibraryView;
  /** Total before filtering — shown when query is non-empty. */
  totalCount: number;
  /** After filtering — shown when query is non-empty. */
  resultCount: number;
  /** Singular noun for the cardinality readout ("pipeline", "dataset"). */
  itemNoun: string;
  /** Optional placeholder text override. */
  placeholder?: string;
}

export function LibraryToolbar({
  view, totalCount, resultCount, itemNoun, placeholder,
}: ToolbarProps) {
  const filtered = view.query.trim().length > 0;
  // Show the toolbar even when small — it's compact, and growing
  // libraries shouldn't suddenly sprout new chrome at threshold N.
  const showCount = useMemo(
    () => filtered ? `${resultCount.toLocaleString()} of ${totalCount.toLocaleString()} ${itemNoun}${totalCount === 1 ? "" : "s"}`
                   : `${totalCount.toLocaleString()} ${itemNoun}${totalCount === 1 ? "" : "s"}`,
    [filtered, resultCount, totalCount, itemNoun],
  );

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
      {/* Search input */}
      <label className="flex-1 min-w-0 flex items-center gap-2 rounded-md border border-border bg-card/40 px-2.5 py-1.5 focus-within:border-foreground/40 transition-colors">
        <span className="text-sm select-none" aria-hidden>🔍</span>
        <input
          type="search"
          value={view.query}
          onChange={(e) => view.setQuery(e.target.value)}
          placeholder={placeholder ?? `Search ${itemNoun}s by name…`}
          aria-label={`Search ${itemNoun}s`}
          className="flex-1 min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground/60"
        />
        {view.query && (
          <button
            type="button"
            onClick={() => view.setQuery("")}
            aria-label="Clear search"
            className="text-muted-foreground hover:text-foreground text-xs leading-none px-1"
            title="Clear"
          >
            ✕
          </button>
        )}
      </label>

      {/* Sort chips */}
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground select-none">
          Sort
        </span>
        {(Object.keys(FIELD_META) as SortField[]).map((f) => {
          const active = view.sort.field === f;
          const meta = FIELD_META[f];
          return (
            <button
              key={f}
              type="button"
              onClick={() => view.setSortField(f)}
              title={
                active
                  ? `${meta.tooltip} — click to flip ${view.sort.direction === "asc" ? "↑" : "↓"}`
                  : meta.tooltip
              }
              aria-pressed={active}
              className={[
                "text-[11px] inline-flex items-center gap-1 px-2 py-0.5 rounded-md border transition-colors",
                active
                  ? "border-emerald-400/70 bg-emerald-50/80 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-200"
                  : "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground",
              ].join(" ")}
            >
              <span aria-hidden>{meta.emoji}</span>
              <span>{meta.label}</span>
              {active && (
                <span aria-hidden className="font-mono text-[10px] tabular-nums">
                  {view.sort.direction === "asc" ? "↑" : "↓"}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Cardinality readout — anchors the user when filtering. */}
      <span className="text-xs text-muted-foreground tabular-nums shrink-0">
        {showCount}
      </span>
    </div>
  );
}

/**
 * Round-5 W5 finding: there was no notion of "recent items" anywhere in
 * DIG. The command palette reset to an alphabetical list every time;
 * the home page showed only static workflow tiles regardless of how many
 * pipelines the user already had; the welcome card disappeared the
 * moment a user owned a single dataset.
 *
 * This module is the canonical store. It keeps small per-kind FIFO
 * caches in localStorage and exposes a uniform read/write surface. The
 * caps are intentionally low — recency is a navigation aid, not a
 * full history.
 */

export type RecentKind = "pipeline" | "dataset" | "run";

export interface RecentItem {
  id: string;
  /** Display label, captured at touch time so a deleted item still
   *  reads sensibly in the palette / home recent panel. */
  label: string;
  /** ISO timestamp of the last access. Sort descending. */
  ts: string;
}

const CAP_PER_KIND = 10;
const STORAGE_KEY = "dig.recent.v1";

interface RecentStore {
  pipeline: RecentItem[];
  dataset: RecentItem[];
  run: RecentItem[];
}

function emptyStore(): RecentStore {
  return { pipeline: [], dataset: [], run: [] };
}

function read(): RecentStore {
  if (typeof window === "undefined") return emptyStore();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as Partial<RecentStore>;
    return {
      pipeline: Array.isArray(parsed.pipeline) ? parsed.pipeline : [],
      dataset: Array.isArray(parsed.dataset) ? parsed.dataset : [],
      run: Array.isArray(parsed.run) ? parsed.run : [],
    };
  } catch {
    return emptyStore();
  }
}

function write(store: RecentStore): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* quota exceeded or storage disabled — fail soft */
  }
}

/** Touch an item: insert at the head, dedupe by id, cap at CAP_PER_KIND. */
export function touchRecent(kind: RecentKind, id: string, label: string): void {
  if (!id) return;
  const store = read();
  const list = store[kind].filter((it) => it.id !== id);
  list.unshift({ id, label, ts: new Date().toISOString() });
  store[kind] = list.slice(0, CAP_PER_KIND);
  write(store);
}

/** Read the most-recent items for one kind (head first). */
export function getRecent(kind: RecentKind): RecentItem[] {
  return read()[kind];
}

/** Remove a specific item (e.g. after a delete). */
export function forgetRecent(kind: RecentKind, id: string): void {
  const store = read();
  store[kind] = store[kind].filter((it) => it.id !== id);
  write(store);
}

/** Wipe everything. */
export function clearRecent(): void {
  write(emptyStore());
}

// ---- Favourites / pinning (Round-5 W5) -----------------------------------

const FAV_STORAGE_KEY = "dig.favorites.v1";

interface FavoriteStore {
  pipeline: string[];
  dataset: string[];
}

function readFavs(): FavoriteStore {
  if (typeof window === "undefined") return { pipeline: [], dataset: [] };
  try {
    const raw = window.localStorage.getItem(FAV_STORAGE_KEY);
    if (!raw) return { pipeline: [], dataset: [] };
    const parsed = JSON.parse(raw) as Partial<FavoriteStore>;
    return {
      pipeline: Array.isArray(parsed.pipeline) ? parsed.pipeline : [],
      dataset: Array.isArray(parsed.dataset) ? parsed.dataset : [],
    };
  } catch {
    return { pipeline: [], dataset: [] };
  }
}

function writeFavs(s: FavoriteStore): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(FAV_STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* fail soft */
  }
}

export function isFavorite(kind: "pipeline" | "dataset", id: string): boolean {
  return readFavs()[kind].includes(id);
}

export function toggleFavorite(kind: "pipeline" | "dataset", id: string): boolean {
  const s = readFavs();
  const set = new Set(s[kind]);
  if (set.has(id)) {
    set.delete(id);
  } else {
    set.add(id);
  }
  s[kind] = Array.from(set);
  writeFavs(s);
  return set.has(id);
}

export function listFavorites(kind: "pipeline" | "dataset"): string[] {
  return readFavs()[kind];
}

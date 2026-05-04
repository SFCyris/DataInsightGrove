"use client";

import { useEffect, useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";

export type ExpertiseLevel = "beginner" | "builder" | "engineer";

export const EXPERTISE_RANK: Record<ExpertiseLevel, number> = {
  beginner: 0,
  builder: 1,
  engineer: 2,
};

export const EXPERTISE_LABEL: Record<ExpertiseLevel, string> = {
  beginner: "🌱 Beginner",
  builder: "🪴 Builder",
  engineer: "🌳 Engineer",
};

export const EXPERTISE_DESCRIPTION: Record<ExpertiseLevel, string> = {
  beginner: "Curated 12-step library, plain-English AI, single-tab side panel.",
  builder: "Full 51-step library, side-by-side diff, full AI features. Daily-driver mode.",
  engineer: "Live SQL toggle, lineage graph, raw JSON, auto-review on save, dev ribbon.",
};

export const AUTO_PROMOTE_THRESHOLD = 25;

export interface Settings {
  theme: Theme;
  /** DuckDB-WASM sample size for live preview (rows). */
  sampleRows: number;
  /** Auto-recompute browser preview on every doc change. */
  livePreview: boolean;
  /** Whether to show the dev-only debug ribbon (run timing, etc.). */
  devRibbon: boolean;
  /** Progressive-disclosure mode — gates surface area and AI verbosity. */
  expertiseLevel: ExpertiseLevel;
  /** When false, the user picked manually; never auto-promote again. */
  expertiseAuto: boolean;
  /** Increments on step add / run / edit; auto-promotes Beginner→Builder when ≥25. */
  actionCount: number;
  /** Compact grid headers — hides inline sparklines + summary stats. */
  compactHeaders: boolean;
}

const DEFAULTS: Settings = {
  theme: "system",
  sampleRows: 100_000,
  livePreview: true,
  devRibbon: false,
  expertiseLevel: "beginner",
  expertiseAuto: true,
  actionCount: 0,
  compactHeaders: false,
};

const KEY = "dig.settings.v1";

// Tiny external store so settings stay in sync across components without a
// React Context provider (works in client components, no SSR ceremony).
let current: Settings = { ...DEFAULTS };
let initialised = false;
const listeners = new Set<() => void>();

function load(): Settings {
  if (typeof window === "undefined") return { ...DEFAULTS };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<Settings>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return { ...DEFAULTS };
  }
}

function persist() {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* ignore */
  }
}

function notify() {
  for (const fn of listeners) fn();
}

function ensureInit() {
  if (initialised || typeof window === "undefined") return;
  current = load();
  initialised = true;
  applyTheme(current.theme);
  // Cross-tab sync
  window.addEventListener("storage", (e) => {
    if (e.key !== KEY) return;
    current = load();
    applyTheme(current.theme);
    notify();
  });
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const sysDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const wantDark = theme === "dark" || (theme === "system" && sysDark);
  root.classList.toggle("dark", wantDark);
  root.style.colorScheme = wantDark ? "dark" : "light";
}

export function getSettings(): Settings {
  ensureInit();
  return current;
}

export function setSettings(patch: Partial<Settings>): void {
  ensureInit();
  current = { ...current, ...patch };
  if ("theme" in patch && patch.theme) applyTheme(patch.theme);
  persist();
  notify();
}

function subscribe(cb: () => void): () => void {
  ensureInit();
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getServerSnapshot(): Settings {
  return DEFAULTS;
}

export function useSettings(): Settings {
  return useSyncExternalStore(subscribe, getSettings, getServerSnapshot);
}

/**
 * Hook for progressive-disclosure mode gating.
 *
 * `level` is the current expertise mode.
 * `isAtLeast(target)` returns true if the user is at or above the target tier.
 * `setLevel(level)` switches mode manually (and disables auto-promotion).
 *
 * Use in components like:
 *   const { isAtLeast } = useExpertise();
 *   {isAtLeast("engineer") && <LiveSqlToggle />}
 */
export function useExpertise() {
  const settings = useSettings();
  const level = settings.expertiseLevel;
  return {
    level,
    auto: settings.expertiseAuto,
    actionCount: settings.actionCount,
    isAtLeast(target: ExpertiseLevel): boolean {
      return EXPERTISE_RANK[level] >= EXPERTISE_RANK[target];
    },
    isExactly(target: ExpertiseLevel): boolean {
      return level === target;
    },
    setLevel(next: ExpertiseLevel) {
      setSettings({ expertiseLevel: next, expertiseAuto: false });
    },
    setLevelKeepAuto(next: ExpertiseLevel) {
      setSettings({ expertiseLevel: next });
    },
  };
}

/**
 * Bumps the action counter and auto-promotes Beginner → Builder when the
 * threshold is crossed (only if `expertiseAuto` is still true).
 *
 * Call from step-add, step-edit, run-start sites:
 *   recordAction(2)  // step add
 *   recordAction(3)  // run
 *   recordAction(1)  // step edit
 *
 * Returns true if a promotion happened (caller may show a Sonner toast).
 */
export function recordAction(weight = 1): boolean {
  ensureInit();
  const next = current.actionCount + weight;
  let promoted = false;
  let nextLevel = current.expertiseLevel;
  if (
    current.expertiseAuto &&
    current.expertiseLevel === "beginner" &&
    next >= AUTO_PROMOTE_THRESHOLD
  ) {
    nextLevel = "builder";
    promoted = true;
  }
  current = { ...current, actionCount: next, expertiseLevel: nextLevel };
  persist();
  notify();
  return promoted;
}

/** Listen to system color-scheme changes when theme is 'system'. */
export function useSystemThemeWatcher() {
  const settings = useSettings();
  useEffect(() => {
    if (settings.theme !== "system" || typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const fn = () => applyTheme(settings.theme);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, [settings.theme]);
}

"use client";

import { useEffect, useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";

export interface Settings {
  theme: Theme;
  /** DuckDB-WASM sample size for live preview (rows). */
  sampleRows: number;
  /** Auto-recompute browser preview on every doc change. */
  livePreview: boolean;
  /** Whether to show the dev-only debug ribbon (run timing, etc.). */
  devRibbon: boolean;
}

const DEFAULTS: Settings = {
  theme: "system",
  sampleRows: 100_000,
  livePreview: true,
  devRibbon: false,
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

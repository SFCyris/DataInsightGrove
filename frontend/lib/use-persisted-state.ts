"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useState backed by localStorage, namespaced by a stable key.
 *
 * Reads on first mount. Writes are debounced 200ms so a slider in flight
 * doesn't spam the storage. Falls back to in-memory state on SSR or when
 * localStorage is denied (Safari private mode).
 *
 * Usage:
 *   const [tab, setTab] = usePersistedState("dig.editor.tab.<pipelineId>", "params");
 */
export function usePersistedState<T>(
  key: string,
  initial: T,
): [T, (next: T | ((cur: T) => T)) => void] {
  const [val, setVal] = useState<T>(initial);
  const initRead = useRef(false);

  // Read once on mount.
  useEffect(() => {
    if (initRead.current) return;
    initRead.current = true;
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) setVal(JSON.parse(raw) as T);
    } catch {
      /* malformed entry → keep initial */
    }
  }, [key]);

  // Debounced write.
  const writeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!initRead.current) return;
    if (typeof window === "undefined") return;
    if (writeTimer.current) clearTimeout(writeTimer.current);
    writeTimer.current = setTimeout(() => {
      try {
        window.localStorage.setItem(key, JSON.stringify(val));
      } catch {
        /* quota exceeded or denied */
      }
    }, 200);
    return () => {
      if (writeTimer.current) clearTimeout(writeTimer.current);
    };
  }, [key, val]);

  const set = useCallback((next: T | ((cur: T) => T)) => {
    setVal((prev) => (typeof next === "function" ? (next as (c: T) => T)(prev) : next));
  }, []);
  return [val, set];
}

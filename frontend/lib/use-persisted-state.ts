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

  // Read on mount AND whenever the key changes.
  //
  // `initRead` used to latch true forever, so a key change skipped the read
  // while the write effect below still fired — persisting the OLD key's value
  // under the NEW key. Switching between two pipelines silently copied one's
  // run-sample preference onto the other. Track which key we've read instead
  // of whether we've read at all.
  const readForKey = useRef<string | null>(null);
  useEffect(() => {
    if (readForKey.current === key) return;
    readForKey.current = key;
    initRead.current = true;
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(key);
      // Reset to `initial` when the new key has nothing stored, so the previous
      // key's value can't linger in state and get written out.
      setVal(raw !== null ? (JSON.parse(raw) as T) : initial);
    } catch {
      setVal(initial);
    }
    // `initial` is intentionally omitted — callers pass object literals, and
    // depending on it would re-run this on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Debounced write.
  const writeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!initRead.current) return;
    // Never write before this key has been read — otherwise the outgoing
    // value is flushed into the incoming key.
    if (readForKey.current !== key) return;
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

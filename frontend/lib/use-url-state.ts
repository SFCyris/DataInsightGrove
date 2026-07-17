"use client";

/**
 * URL-encoded interactive state.
 *
 * Hook to sync a JSON-serialisable state object to a single URL search
 * parameter. Lets users:
 *   - Refresh the page and keep their drill / filter / annotation state.
 *   - Copy a "share link" that reproduces the exact view for a colleague
 *     (or future-them).
 *
 * Design rules followed:
 *  - One state blob per logical surface (Sankey, DNA, …) under a named
 *    URL key. Keeps the URL human-scannable for the most-common cases
 *    and round-trippable for everything else.
 *  - Debounced writes (180 ms) so dragging zoom doesn't spam the
 *    history stack.
 *  - `history.replaceState` not `pushState` — back-button shouldn't
 *    walk through every drill click.
 *  - Graceful decode: any parse error falls back to default. URL is
 *    user-mutable; we never crash on garbage input.
 *  - SSR-safe: every `window` access is gated by `typeof window`.
 *  - URL-safe base64 of JSON. JSON keeps the doors open for nested
 *    structures; base64-url gives us a copy-pasteable token without
 *    URL-encoding noise.
 */
import { useCallback, useEffect, useRef, useState } from "react";

/** URL-safe base64 with no padding. Strips `=`, swaps `+/` for `-_`. */
function b64urlEncode(s: string): string {
  if (typeof window === "undefined") return "";
  return btoa(unescape(encodeURIComponent(s)))
    .replace(/=+$/, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

function b64urlDecode(s: string): string {
  if (typeof window === "undefined") return "";
  const padded =
    s.replace(/-/g, "+").replace(/_/g, "/")
    + "===".slice(0, (4 - (s.length % 4)) % 4);
  try {
    return decodeURIComponent(escape(atob(padded)));
  } catch {
    return "";
  }
}

function readURLParam(key: string): string | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  return params.get(key);
}

function writeURLParam(key: string, encoded: string | null): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (encoded === null || encoded === "") {
    url.searchParams.delete(key);
  } else {
    url.searchParams.set(key, encoded);
  }
  window.history.replaceState(null, "", url.toString());
}

export interface URLStateOptions<T> {
  /** When the encoded blob is identical to the default state, omit
   *  the param entirely so URLs stay clean for default views. */
  omitWhenDefault?: boolean;
  /** Custom comparator for "is this the default?" — default is JSON
   *  shallow compare. Useful when state contains Sets/Maps. */
  isDefault?: (state: T) => boolean;
  /** Debounce window for URL writes. Default 180 ms — fast enough
   *  that "copy link" right after a drag captures the new state. */
  debounceMs?: number;
}

/**
 * Same shape as React.useState, but the second tuple slot also persists
 * to a URL param. Third tuple slot exposes the current encoded token so
 * a "Copy link" button can read it directly.
 */
export function useURLState<T>(
  key: string,
  defaultValue: T,
  options: URLStateOptions<T> = {},
): [T, (v: T | ((prev: T) => T)) => void, string | null] {
  const { omitWhenDefault = true, isDefault, debounceMs = 180 } = options;

  // Decode the initial state from the URL on first render. Done lazily
  // inside useState so the URL read doesn't run during SSR.
  const [state, setStateInternal] = useState<T>(() => {
    const raw = readURLParam(key);
    if (!raw) return defaultValue;
    const json = b64urlDecode(raw);
    if (!json) return defaultValue;
    try {
      return JSON.parse(json) as T;
    } catch {
      return defaultValue;
    }
  });

  // Track the latest encoded form so the "copy link" button can read it
  // synchronously without recomputing.
  const [encoded, setEncoded] = useState<string | null>(() => readURLParam(key));

  // Debounce the URL writes. We batch rapid setState calls (e.g. zoom
  // drags) into a single replaceState at the end of the burst.
  const writeTimer = useRef<number | null>(null);

  const setState = useCallback(
    (v: T | ((prev: T) => T)) => {
      setStateInternal((prev) => {
        const next =
          typeof v === "function" ? (v as (p: T) => T)(prev) : v;
        // Schedule URL write outside the React commit so we don't tear
        // the renderer.
        if (writeTimer.current !== null) {
          window.clearTimeout(writeTimer.current);
        }
        writeTimer.current = window.setTimeout(() => {
          const isDefaultNow = isDefault
            ? isDefault(next)
            : JSON.stringify(next) === JSON.stringify(defaultValue);
          if (omitWhenDefault && isDefaultNow) {
            writeURLParam(key, null);
            setEncoded(null);
          } else {
            const enc = b64urlEncode(JSON.stringify(next));
            writeURLParam(key, enc);
            setEncoded(enc);
          }
        }, debounceMs);
        return next;
      });
    },
    [key, defaultValue, omitWhenDefault, isDefault, debounceMs],
  );

  // Cleanup timer on unmount.
  useEffect(() => {
    return () => {
      if (writeTimer.current !== null) {
        window.clearTimeout(writeTimer.current);
      }
    };
  }, []);

  return [state, setState, encoded];
}

/**
 * Helper that builds a full shareable URL for the current page,
 * preserving the active param, optionally with extra query params
 * mixed in. Used by "Copy link" buttons.
 */
export function buildShareLink(extraParams: Record<string, string> = {}): string {
  if (typeof window === "undefined") return "";
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(extraParams)) {
    if (v === "") url.searchParams.delete(k);
    else url.searchParams.set(k, v);
  }
  return url.toString();
}

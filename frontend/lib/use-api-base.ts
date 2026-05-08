"use client";

/**
 * Hydration-safe API base URL for rendering into the DOM.
 *
 * The eagerly-evaluated `API_BASE` constant resolves to different values
 * on server and client (SSR can't see `window.location`), which causes
 * a React hydration mismatch when used inside `<a href={…}>`, `<form
 * action={…}>`, etc.
 *
 * This hook returns:
 *   - On first render (and during SSR):    SSR_SAFE_API_BASE
 *     (env var or `http://127.0.0.1:8090` fallback). Server and client
 *     agree → no hydration error.
 *   - After mount on the client:           the real `API_BASE` (which
 *     factors in `window.location.hostname`), so the link works for
 *     LAN visitors who loaded the page via `http://10.0.0.5:3000`.
 *
 * Pair it with `<a suppressHydrationWarning>` if the consumer wants
 * the post-mount swap to be silent.
 */
import { useEffect, useState } from "react";
import { API_BASE, SSR_SAFE_API_BASE } from "@/lib/api/client";

export function useApiBase(): string {
  const [base, setBase] = useState<string>(SSR_SAFE_API_BASE);
  useEffect(() => {
    if (API_BASE !== base) setBase(API_BASE);
    // Run once on mount; API_BASE is a module-level constant.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return base;
}

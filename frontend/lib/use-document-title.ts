"use client";

import { useEffect } from "react";

/**
 * Set `document.title` for a client-component route. The Next.js
 * `metadata` export only works on server components; every DIG route is
 * "use client" so we synthesize the same effect at runtime.
 *
 * Round-6 UX#1 finding: every sub-route inherited the layout default
 * "DataInsightGrove™ · DIG", so multiple DIG tabs were indistinguishable.
 */
export function useDocumentTitle(title: string | undefined): void {
  useEffect(() => {
    if (!title) return;
    const prev = document.title;
    document.title = `${title} · DataInsightGrove™`;
    return () => {
      document.title = prev;
    };
  }, [title]);
}

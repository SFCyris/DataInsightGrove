"use client";

import { useEffect, useState } from "react";
import { isDemoMode } from "@/lib/demo-mode";

/**
 * DemoBanner — top-of-page strip shown only on browser-demo builds.
 *
 * Goals:
 *   1. Set the user's expectation: "This is a sandbox; data won't persist."
 *   2. Drive the conversion path: a clear CTA to install for real.
 *   3. Be dismissable (per session) so the experience isn't naggy after
 *      the first read.
 *
 * In production builds this component renders nothing — the build-time
 * flag short-circuits before any DOM work — so it's safe to mount
 * unconditionally in the root layout.
 */
export function DemoBanner() {
  const [dismissed, setDismissed] = useState(false);

  // Read once on mount. We don't sync to localStorage on purpose — a demo
  // should re-introduce itself on a hard refresh; otherwise users who
  // come back days later forget what build they're on and get surprised
  // when their pipeline is missing.
  useEffect(() => {
    try {
      setDismissed(sessionStorage.getItem("dig.demo-banner.dismissed") === "1");
    } catch {
      /* private browsing / SSR — fine */
    }
  }, []);

  if (!isDemoMode() || dismissed) return null;

  return (
    <div
      role="region"
      aria-label="Browser demo notice"
      className="w-full bg-amber-100 border-b border-amber-300 text-amber-900 dark:bg-amber-950 dark:border-amber-700 dark:text-amber-100"
    >
      <div className="max-w-6xl mx-auto px-4 py-1.5 flex items-center gap-3 text-xs sm:text-sm">
        <span className="select-none" aria-hidden>🧪</span>
        <p className="flex-1 leading-relaxed">
          <strong>Browser demo.</strong> Pipelines and datasets live in your browser only —
          they won't sync, run on a backend, or call AI. Want all of that?{" "}
          <a
            href="https://github.com/SFCyris/DataInsightGrove#install"
            className="underline underline-offset-2 hover:text-amber-700 dark:hover:text-amber-50"
            target="_blank"
            rel="noreferrer"
          >
            Install DIG locally →
          </a>
        </p>
        <button
          type="button"
          onClick={() => {
            try {
              sessionStorage.setItem("dig.demo-banner.dismissed", "1");
            } catch {
              /* ignore */
            }
            setDismissed(true);
          }}
          aria-label="Dismiss demo notice"
          className="text-amber-700 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-50 px-1.5 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

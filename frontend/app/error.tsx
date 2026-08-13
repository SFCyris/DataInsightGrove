"use client";

/**
 * Route-level error boundary.
 *
 * Before this file existed there was no React error boundary anywhere in the
 * app (no `error.tsx`, no `global-error.tsx`, no `componentDidCatch`). A
 * single render-time throw — an unmapped key in a lookup table, an
 * unexpected shape from the API — blanked the whole page, and in the editor
 * it also took the in-memory undo stack with it. This keeps the chrome alive,
 * explains what happened, and offers a real way back.
 *
 * Next 16.2 passes BOTH `unstable_retry` and the older `reset`. We prefer
 * `unstable_retry` and fall back to `reset`: the `unstable_` prefix is a
 * standing warning that the name can change, and a rename would otherwise
 * throw a TypeError inside the error boundary itself — the one component that
 * must never throw.
 */

import { useEffect } from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";

export default function Error({
  error,
  unstable_retry,
  reset,
}: {
  error: Error & { digest?: string };
  unstable_retry?: () => void;
  reset?: () => void;
}) {
  const retry = unstable_retry ?? reset;
  useEffect(() => {
    // Surface it for anyone with the console open; there is no telemetry
    // sink in a self-hosted install.
    console.error("[dig] route error:", error);
  }, [error]);

  return (
    <main
      id="main"
      tabIndex={-1}
      className="flex-1 flex items-center justify-center p-6"
    >
      {/* The boundary swaps in without a navigation, so nothing would be
          announced otherwise — a screen-reader user would just find the page
          silently replaced. */}
      <div
        role="alert"
        aria-live="assertive"
        className="max-w-md w-full rounded-lg border border-border bg-card p-6 text-center"
      >
        <div className="text-3xl mb-2" aria-hidden="true">
          🌵
        </div>
        <h1 className="text-lg font-semibold mb-1">This page hit a snag</h1>
        <p className="text-sm text-muted-foreground mb-4">
          Something in this view failed to render. Your data is safe — nothing was
          saved or changed by this error.
        </p>
        {error.message && (
          <p className="text-xs font-mono text-muted-foreground bg-muted rounded p-2 mb-4 text-left break-words">
            {error.message}
            {error.digest && <span className="opacity-60"> · {error.digest}</span>}
          </p>
        )}
        <div className="flex items-center justify-center gap-2">
          {retry && <Button onClick={() => retry()}>↻ Try again</Button>}
          <Link href="/" className={buttonVariants({ variant: "ghost" })}>
            🏠 Home
          </Link>
        </div>
      </div>
    </main>
  );
}

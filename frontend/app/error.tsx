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
 * Next 16 passes `unstable_retry` (not the older `reset`) to re-render the
 * segment without a full reload, which is what preserves surrounding state.
 */

import { useEffect } from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
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
      <div className="max-w-md w-full rounded-lg border border-border bg-card p-6 text-center">
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
          <Button onClick={() => unstable_retry()}>↻ Try again</Button>
          <Link href="/" className={buttonVariants({ variant: "ghost" })}>
            🏠 Home
          </Link>
        </div>
      </div>
    </main>
  );
}

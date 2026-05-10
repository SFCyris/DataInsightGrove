"use client";

import { useEffect, useState } from "react";

/**
 * Three-state save indicator: a small colored dot plus tooltip.
 *
 *   amber  — local edits not yet sent
 *   blue   — save in flight (only shown after 250 ms so brief saves stay invisible)
 *   green  — synced
 *
 * Replaces the previous text label which showed "💾 Saving…" for the entire
 * round trip, making 80 ms saves feel like 800 ms ones.
 */
export function SaveIndicator({ dirty, pending }: { dirty: boolean; pending: boolean }) {
  const [showPending, setShowPending] = useState(false);

  // Only show the "saving" state after 250 ms of pending. Most saves are
  // faster than that and never need to flash a label at the user.
  useEffect(() => {
    if (!pending) {
      setShowPending(false);
      return;
    }
    const t = setTimeout(() => setShowPending(true), 250);
    return () => clearTimeout(t);
  }, [pending]);

  let color: string, label: string;
  if (dirty) {
    color = "bg-amber-500"; label = "Unsaved edits";
  } else if (showPending) {
    color = "bg-sky-500 animate-pulse"; label = "Saving…";
  } else {
    color = "bg-emerald-500"; label = "Synced";
  }

  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"
      title={label}
      aria-label={label}
    >
      <span className={`inline-block w-2 h-2 rounded-full ${color}`} aria-hidden />
    </span>
  );
}

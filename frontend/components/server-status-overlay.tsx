"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { useServerStatus, type ServerStatus } from "@/lib/server-status";

/**
 * Top-of-page banner that surfaces backend connectivity state.
 *
 * Three observable states (the singleton's `online` state renders nothing):
 *
 *   🔴 down       — server is unreachable; we're polling/retrying. Persists
 *                   until the server answers `/health`.
 *   🟡 connecting — initial page load before the first ping confirms; or
 *                   user just landed on a tab that woke from sleep.
 *   🟢 recovered  — we just reconnected. Shows for ~1.2 s then disappears.
 *
 * Banner is `position: fixed top-0 inset-x-0`, backdrop-blurred, and sits
 * above almost everything (z-[60]) but below modal dialogs (z-50 with backdrop)
 * so a long-running modal interaction isn't ambushed. The skip-link in
 * layout.tsx is z-[100] which is the only intentionally-higher element.
 *
 * "down" deliberately doesn't include a manual retry button — the singleton
 * polls every 1.5 s while down, so the user just waits. Adding a button
 * would invite repeated clicking that doesn't change anything.
 */

interface BannerSpec {
  emoji: string;
  text: string;
  /** Tailwind classes for the colored band. */
  band: string;
  /** Tailwind classes for the text inside. */
  text_cls: string;
  /** True if the bar should pulse (subtle attention without being obnoxious). */
  pulse?: boolean;
}

const SPECS: Record<Exclude<ServerStatus, "online">, BannerSpec> = {
  down: {
    emoji: "🔴",
    text: "Server is unreachable — restarting / retrying…",
    band: "bg-rose-600 dark:bg-rose-700 border-b border-rose-700/50",
    text_cls: "text-white",
    pulse: true,
  },
  connecting: {
    emoji: "⏳",
    text: "Connecting to the server…",
    band: "bg-amber-500 dark:bg-amber-600 border-b border-amber-700/50",
    text_cls: "text-amber-950 dark:text-white",
    pulse: true,
  },
  recovered: {
    emoji: "✅",
    text: "Server is online",
    band: "bg-emerald-500 dark:bg-emerald-600 border-b border-emerald-700/50",
    text_cls: "text-white",
  },
};

export function ServerStatusOverlay() {
  const status = useServerStatus();
  const reduce = useReducedMotion();

  // Track how long we've been in `down` state. We don't actually render this
  // anywhere by default, but it gives the visual a faint "still trying for X
  // seconds" hint — useful when the wait is real (cold-start backends can take
  // 10+ s). Resets to 0 on every status change.
  const [downSince, setDownSince] = useState<number | null>(null);
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (tickerRef.current) clearInterval(tickerRef.current);
    if (status === "down") {
      const start = Date.now();
      setDownSince(0);
      tickerRef.current = setInterval(() => {
        setDownSince(Math.floor((Date.now() - start) / 1000));
      }, 1000);
    } else {
      setDownSince(null);
    }
    return () => {
      if (tickerRef.current) clearInterval(tickerRef.current);
    };
  }, [status]);

  if (status === "online") return null;
  const spec = SPECS[status];

  const initial = reduce ? false : { y: -28, opacity: 0 };
  const animate = { y: 0, opacity: 1 };
  const exit = reduce ? undefined : { y: -28, opacity: 0 };
  const transition = reduce
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 380, damping: 30 };

  return (
    <AnimatePresence>
      <motion.div
        key="server-status-banner"
        role="status"
        aria-live="polite"
        initial={initial}
        animate={animate}
        exit={exit}
        transition={transition}
        className={`fixed top-0 inset-x-0 z-[60] ${spec.band} shadow-md`}
      >
        <div className="max-w-screen-xl mx-auto px-4 py-2 flex items-center justify-center gap-3 text-sm">
          {/* Pulse ring around the emoji for the persistent states. */}
          <span className={`relative inline-flex items-center justify-center ${spec.text_cls}`}>
            {spec.pulse && !reduce && (
              <span
                aria-hidden
                className="absolute inset-0 rounded-full bg-current opacity-30 animate-ping"
              />
            )}
            <span className="relative" aria-hidden>{spec.emoji}</span>
          </span>
          <span className={`font-medium ${spec.text_cls}`}>
            {spec.text}
            {downSince !== null && downSince >= 5 && (
              <span className={`ml-2 opacity-80 font-normal text-xs tabular-nums ${spec.text_cls}`}>
                ({downSince}s)
              </span>
            )}
          </span>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

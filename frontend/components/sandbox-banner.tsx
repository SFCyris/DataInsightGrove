"use client";

import { motion, useReducedMotion } from "motion/react";
import { IS_SANDBOX } from "@/lib/sandbox";

/**
 * Top-of-page banner shown when the build is in sandbox mode.
 * Always-visible CTA to convert sandbox visitors into local installs.
 */
export function SandboxBanner() {
  const reduce = useReducedMotion();
  if (!IS_SANDBOX) return null;
  return (
    <motion.div
      initial={reduce ? false : { y: -32, opacity: 0 }}
      animate={reduce ? { opacity: 1 } : { y: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="bg-emerald-100 dark:bg-emerald-900/30 border-b border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-100 px-4 py-2 text-xs flex items-center gap-3"
      role="status"
    >
      <span aria-hidden className="text-base">🌳</span>
      <span className="flex-1">
        <strong>Sandbox mode</strong> — your data stays in the browser. Some
        steps that need Python (PCA, forecast, image render) are disabled.
      </span>
      <a
        href="https://github.com/SFCyris/DataInsightGrove#quickstart"
        target="_blank"
        rel="noreferrer"
        className="rounded-md border border-emerald-700/60 px-2.5 py-1 hover:bg-emerald-200 dark:hover:bg-emerald-900/60 transition-colors"
      >
        ⚡ Open in your local DIG
      </a>
    </motion.div>
  );
}

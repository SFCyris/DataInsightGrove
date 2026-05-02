"use client";

/**
 * Tiny "ⓘ help" link rendered next to a panel title. Opens
 * docs/getting_started.md at a specific anchor in a new tab.
 *
 * The backend mounts /docs-files/ as a static dir, so the raw markdown file
 * loads in any browser (modern browsers render .md as plain text — fine for
 * a quick reference; we'll add a markdown renderer in a future iteration).
 */

import { motion } from "motion/react";
import { API_BASE } from "@/lib/api/client";

interface Props {
  /** Anchor in the doc, e.g. "the-editor". Without leading '#'. */
  anchor?: string;
  /** What this help is *about* — surfaced as the link tooltip + accessible label. */
  topic: string;
  /** Optional alternate doc path (relative to /docs-files/). Defaults to getting_started.md. */
  doc?: string;
  /** Visual size — 'sm' (default, fits next to a panel title) or 'inline' (in body text). */
  size?: "sm" | "inline";
}

export function HelpLink({ anchor, topic, doc = "getting_started.md", size = "sm" }: Props) {
  const href = anchor
    ? `${API_BASE}/docs-files/${doc}#${anchor}`
    : `${API_BASE}/docs-files/${doc}`;
  const label = `Help: ${topic}`;
  return (
    <motion.a
      href={href}
      target="_blank"
      rel="noreferrer"
      title={label}
      aria-label={label}
      whileHover={{ scale: 1.06 }}
      whileTap={{ scale: 0.94 }}
      className={
        size === "sm"
          ? "inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors leading-none"
          : "underline-offset-2 hover:underline text-muted-foreground hover:text-foreground"
      }
    >
      {size === "sm" ? "ⓘ" : "ⓘ help"}
    </motion.a>
  );
}

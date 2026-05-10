"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

/**
 * Standardized back/home button used across every top-level screen.
 *
 * Always renders an unstyled `<Link>` with a ghost-button look. Pages
 * are expected to place it in the TOP-LEFT of the screen so users
 * always know where to look — same pattern as macOS apps' back arrow,
 * browsers' back button, and the pipeline editor.
 *
 * Defaults to "/" + "Home"; pass `href` + `label` to override (e.g.
 * "← Datasets" inside /datasets/[id]).
 */
export function BackHome({
  href = "/",
  label = "Home",
}: {
  href?: string;
  label?: string;
}) {
  return (
    <Link
      href={href}
      className={buttonVariants({ variant: "ghost", size: "sm" })}
      aria-label={`Back to ${label}`}
    >
      ← {label}
    </Link>
  );
}

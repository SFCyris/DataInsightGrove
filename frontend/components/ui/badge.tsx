/** Status/label chip.
 *
 *  63 `rounded-full` chips existed in ~25 treatments, with FOUR rival status
 *  vocabularies — so the same run rendered differently depending on which
 *  page you opened it from. `tone` is the single vocabulary.
 *
 *  Every tone pairs colour with text (never colour alone), which is what
 *  WCAG 1.4.1 requires — a status conveyed only by hue is invisible to a
 *  colour-blind user and to anyone reading a greyscale screenshot.
 */

import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info" | "running";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-muted text-foreground/80 border-border",
  success: "bg-emerald-500/12 text-emerald-800 dark:text-emerald-300 border-emerald-500/30",
  warning: "bg-amber-500/12 text-amber-800 dark:text-amber-300 border-amber-500/30",
  danger:  "bg-rose-500/12 text-rose-800 dark:text-rose-300 border-rose-500/30",
  info:    "bg-sky-500/12 text-sky-800 dark:text-sky-300 border-sky-500/30",
  running: "bg-sky-500/12 text-sky-800 dark:text-sky-300 border-sky-500/30",
};

export function Badge({
  tone = "neutral", className, ...props
}: React.ComponentProps<"span"> & { tone?: BadgeTone }) {
  return (
    <span
      {...props}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
    />
  );
}

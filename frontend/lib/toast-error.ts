import { toast, type ExternalToast } from "sonner";
import { humanizeSqlError } from "@/lib/humanize-sql-error";

/**
 * Centralized error-toast helper. Two improvements over a raw
 * ``toast.error(prefix + e.message)``:
 *
 *   1. Routes the message through ``humanizeSqlError`` so DuckDB
 *      "Binder Error: Referenced column …" stops leaking into the UI
 *      verbatim. Falls back to the raw message when nothing matches.
 *   2. Defaults the toast duration to **8 s** so users have time to
 *      read multi-clause humanized output. Sonner's 4 s default cuts
 *      off mid-sentence on slow readers.
 *
 * Callers can pass any other Sonner ExternalToast option to override
 * (e.g. ``{ action: { … } }`` for a retry CTA).
 */
export function toastError(
  prefix: string,
  err: unknown,
  options: ExternalToast = {},
): void {
  const message = err instanceof Error ? err.message : String(err);
  const humanized = humanizeSqlError(message, []);
  const display = humanized.title && humanized.title !== message
    ? humanized.title
    : message;
  toast.error(`${prefix}: ${display}`, { duration: 8000, ...options });
}

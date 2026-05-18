/**
 * Shared sonner-toast confirm() replacement.
 *
 * DIG has a brand rule against native `window.confirm()`: it's unstylable,
 * blocks the event loop, and disagrees visually with every other modal
 * surface (which all use sonner / AlertDialog). This helper produces a
 * Promise<boolean> using sonner's action/cancel buttons so any
 * destructive-action handler can stay async without touching JSX.
 *
 * Usage:
 *   if (!(await confirmAction({ title: "Remove X?", description: "…" }))) return;
 *   await api.remove(...);
 */

import { toast } from "sonner";

export interface ConfirmActionOptions {
  /** Short headline shown in bold at the top of the toast. */
  title: string;
  /** Optional sub-line explaining the consequence. */
  description?: string;
  /** Label of the affirmative button. Defaults to "Confirm". */
  confirmLabel?: string;
  /** Label of the dismiss button. Defaults to "Cancel". */
  cancelLabel?: string;
  /** When true (default), the toast styles as a warning. */
  warning?: boolean;
  /** How long the toast stays before silently resolving false. Default 30s. */
  durationMs?: number;
}

export async function confirmAction(opts: ConfirmActionOptions): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    const fn = opts.warning === false ? toast : toast.warning;
    let resolved = false;
    const finish = (value: boolean) => {
      if (resolved) return;
      resolved = true;
      resolve(value);
    };
    const id = fn(opts.title, {
      description: opts.description,
      action: {
        label: opts.confirmLabel ?? "Confirm",
        onClick: () => { finish(true); toast.dismiss(id); },
      },
      cancel: {
        label: opts.cancelLabel ?? "Cancel",
        onClick: () => { finish(false); toast.dismiss(id); },
      },
      duration: opts.durationMs ?? 30_000,
      onDismiss: () => finish(false),
      onAutoClose: () => finish(false),
    });
  });
}

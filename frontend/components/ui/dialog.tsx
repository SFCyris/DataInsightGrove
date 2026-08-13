"use client";

/**
 * The one modal.
 *
 * Replaces 26 hand-rolled overlays that had drifted into 5 different scrim
 * fills (`black/30`, `/40`, `/50`, `/60`, `foreground/40`), 3 radii, several
 * z-index tiers, and two incompatible centring idioms — and, more seriously,
 * inconsistent behaviour: focus trapped in 1 of 26, restored in 2, scroll
 * locked in 1, Escape missing entirely in 6.
 *
 * Correct-by-construction here: focus trap + restore, Escape arbitration
 * (only the top-most overlay closes), scroll lock, `aria-modal`, a labelled
 * title, and a viewport-safe `max-w`/`max-h` so a fixed-width panel can never
 * spill past the screen edge unreachably.
 */

import { useId, useRef } from "react";
import { cn } from "@/lib/utils";
import { useDialogBehavior } from "./use-dialog-behavior";
import { Z } from "./z";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name. Rendered as the heading unless `hideTitle`. */
  title: React.ReactNode;
  hideTitle?: boolean;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  /** Tailwind max-width class for the panel. */
  size?: "sm" | "md" | "lg" | "xl";
  /** Use `alertdialog` for destructive confirmations. */
  role?: "dialog" | "alertdialog";
  className?: string;
}

const SIZES: Record<NonNullable<DialogProps["size"]>, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-2xl",
};

export function Dialog({
  open,
  onClose,
  title,
  hideTitle,
  description,
  children,
  footer,
  size = "md",
  role = "dialog",
  className,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const descId = useId();

  useDialogBehavior(open, onClose, panelRef);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 flex items-center justify-center p-4"
      style={{ zIndex: Z.modal }}
      // Backdrop click closes. Pointer-down-then-drag out of the panel must
      // NOT close, so key off the target being the backdrop itself.
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" />
      <div
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={cn(
          // `max-w-[92vw]` + `max-h-[85vh]` keep the panel on-screen at every
          // viewport — seven dialogs previously used a fixed px width with no
          // guard and spilled past the edge with no way to scroll to them.
          "relative w-full max-w-[92vw] max-h-[85vh] overflow-y-auto rounded-lg border border-border bg-card text-card-foreground shadow-2xl p-5 outline-none",
          SIZES[size],
          className,
        )}
      >
        <h2 id={titleId} className={cn("text-base font-semibold", hideTitle && "sr-only")}>
          {title}
        </h2>
        {description && (
          <p id={descId} className="mt-1 text-sm text-muted-foreground">
            {description}
          </p>
        )}
        {children && <div className="mt-3">{children}</div>}
        {footer && <div className="mt-4 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

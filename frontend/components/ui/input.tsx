"use client";

/**
 * Text input with a label that is actually associated with it.
 *
 * 61 of ~118 form controls in the app had no accessible name. The cause was
 * three wrapper components that rendered their label as a `<p>` or closed the
 * `<label>` before `{children}`, so the association never existed — including
 * on the HMAC-secret and JDBC-URL fields, and the pipeline title on the
 * editor's primary screen.
 *
 * `useId` + `htmlFor` here means every consumer gets it right by default, and
 * error text is wired through `aria-describedby` / `aria-invalid` — of which
 * the codebase previously had zero.
 */

import { useId } from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends Omit<React.ComponentProps<"input">, "id"> {
  label: React.ReactNode;
  /** Visually hide the label but keep it for assistive tech. */
  hideLabel?: boolean;
  hint?: React.ReactNode;
  error?: string | null;
}

export function Input({
  label, hideLabel, hint, error, className, ...props
}: InputProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy = [hint ? hintId : null, error ? errId : null]
    .filter(Boolean).join(" ") || undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={cn("text-sm font-medium", hideLabel && "sr-only")}>
        {label}
      </label>
      <input
        {...props}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          // `--input`/`--border` measure 1.26:1 against the card in light mode
          // — a boundary you cannot see (WCAG 1.4.11 wants 3:1). Use the
          // stronger foreground-tinted border so the field is locatable.
          "rounded-md border border-foreground/25 bg-background px-3 py-2 text-sm",
          "outline-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:border-ring",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          error && "border-destructive",
          className,
        )}
      />
      {hint && !error && (
        <p id={hintId} className="text-xs text-muted-foreground">{hint}</p>
      )}
      {error && (
        // role="alert" so the message is announced when it appears — the app
        // had zero of these, so validation failures were silent to a screen
        // reader (and often rendered 160 lines away from the field).
        <p id={errId} role="alert" className="text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}

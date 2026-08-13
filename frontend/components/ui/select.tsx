"use client";

/** Native select with a properly associated label. 32 raw `<select>`s existed
 *  across ~18 literal class strings; two in Settings were entirely unstyled
 *  next to styled siblings. */

import { useId } from "react";
import { cn } from "@/lib/utils";

export interface SelectProps extends Omit<React.ComponentProps<"select">, "id"> {
  label: React.ReactNode;
  hideLabel?: boolean;
  hint?: React.ReactNode;
}

export function Select({ label, hideLabel, hint, className, children, ...props }: SelectProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={cn("text-sm font-medium", hideLabel && "sr-only")}>
        {label}
      </label>
      <select
        {...props}
        id={id}
        aria-describedby={hint ? hintId : undefined}
        className={cn(
          "rounded-md border border-foreground/25 bg-background px-3 py-2 text-sm",
          "outline-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:border-ring",
          "disabled:opacity-50",
          className,
        )}
      >
        {children}
      </select>
      {hint && <p id={hintId} className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

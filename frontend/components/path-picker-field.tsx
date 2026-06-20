"use client";

import { useState } from "react";
import { DirectoryPickerModal } from "@/components/directory-picker-modal";

/**
 * A path text input paired with a "📁 Browse" button that opens the
 * server-side picker. Use this anywhere the user types a filesystem path —
 * a JDBC JAR, an output directory, a cert file, etc.
 *
 * Behaviour the picker gives you for free:
 *   - opens at the directory of the current value when one is set, else at
 *     `fallbackPath` (or $HOME if that's empty too);
 *   - file mode filters by `extensions` and returns a file path;
 *   - directory mode returns a directory path.
 */
interface Props {
  value: string;
  onChange: (next: string) => void;
  mode?: "file" | "directory";
  /** File-mode extension allow-list, e.g. [".jar"]. */
  extensions?: string[];
  /** Where to open the picker when `value` is empty. Defaults to $HOME
   *  (the backend resolves an empty path to the user's home dir). */
  fallbackPath?: string;
  placeholder?: string;
  /** Picker heading hint, e.g. "JDBC driver JAR". */
  forLabel?: string;
  /** Forwarded to the <input> (id, disabled, name, etc.). */
  inputProps?: React.InputHTMLAttributes<HTMLInputElement>;
  /** Monospace the path input (default true — paths read better mono). */
  mono?: boolean;
  className?: string;
}

export function PathPickerField({
  value, onChange, mode = "file", extensions, fallbackPath = "",
  placeholder, forLabel, inputProps, mono = true, className,
}: Props) {
  const [open, setOpen] = useState(false);
  // Open the picker at the current value if set, otherwise the fallback.
  const initialPath = value?.trim() || fallbackPath;
  const disabled = inputProps?.disabled;

  return (
    <>
      {/* Input + Browse share ONE bordered box (same pattern as the
          password field) so the field's outer edge lines up exactly with
          every other full-width input in the form — the Browse button
          lives inside the box on the right rather than widening the row. */}
      <div
        className={[
          "flex items-stretch w-full rounded-md border border-input bg-background overflow-hidden",
          "focus-within:ring-2 focus-within:ring-ring/40",
          disabled ? "opacity-60" : "",
          className ?? "",
        ].join(" ")}
      >
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="off"
          className={[
            "flex-1 min-w-0 bg-transparent px-2 py-1 text-sm outline-none",
            mono ? "font-mono" : "",
          ].join(" ")}
          {...inputProps}
        />
        <button
          type="button"
          onClick={() => setOpen(true)}
          disabled={disabled}
          title={mode === "file" ? "Browse for a file on the server" : "Browse for a folder on the server"}
          className="shrink-0 flex items-center gap-1 px-2.5 text-xs border-l border-input text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors disabled:cursor-not-allowed"
        >
          <span aria-hidden>📁</span> Browse
        </button>
      </div>
      <DirectoryPickerModal
        open={open}
        initialPath={initialPath}
        mode={mode}
        extensions={extensions}
        forLabel={forLabel}
        onClose={() => setOpen(false)}
        onSelect={(picked) => onChange(picked)}
      />
    </>
  );
}

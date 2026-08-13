"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/button";

/**
 * Tiny modal — title + lede + single text input + Confirm/Cancel.
 *
 * Reused by:
 *   - 💾 Save (label is optional → "" returned as null)
 *   - 📋 Save As (label is required → must be non-empty)
 *
 * Keeps the dialog UX identical across both flows so the muscle memory
 * transfers.
 */
interface Props {
  open: boolean;
  title: string;
  lede?: string;
  placeholder?: string;
  defaultValue?: string;
  confirmLabel: string;
  /** When true, the Confirm button is disabled until the user types. */
  required?: boolean;
  onConfirm: (value: string | null) => void;
  onClose: () => void;
}

export function LabelPromptDialog({
  open, title, lede, placeholder, defaultValue, confirmLabel, required,
  onConfirm, onClose,
}: Props) {
  const [value, setValue] = useState(defaultValue ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setValue(defaultValue ?? "");
      // Focus + select-all so the user can either confirm the default or
      // type-to-replace without an extra Cmd-A. Wait one tick for the
      // motion animation to mount the input.
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 60);
    }
  }, [open, defaultValue]);

  const trimmed = value.trim();
  const canConfirm = required ? trimmed.length > 0 : true;

  const submit = () => {
    if (!canConfirm) return;
    onConfirm(trimmed || null);
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="lp-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/30"
          />
          <motion.div
            key="lp-dialog"
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 360, damping: 32 }}
            role="dialog"
            aria-label={title}
            className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 max-w-[92vw] w-[460px] rounded-xl border border-border bg-card shadow-2xl p-5"
          >
            <header className="mb-3">
              <h2 className="text-base font-semibold leading-tight">{title}</h2>
              {lede && (
                <p className="text-[12px] text-muted-foreground mt-1 leading-relaxed">
                  {lede}
                </p>
              )}
            </header>
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
                if (e.key === "Escape") onClose();
              }}
              placeholder={placeholder}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/40"
            />
            <div className="flex justify-end gap-2 mt-4">
              <Button size="sm" variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button size="sm" onClick={submit} disabled={!canConfirm}>
                {confirmLabel}
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

"use client";

/**
 * The behaviour every modal needs, in one place.
 *
 * The app had 26 hand-rolled overlays. Measured across them: focus was trapped
 * in 1, focus was restored on close in 2, body scroll was locked in 1, and 6
 * had no Escape handler at all — while the shortcuts cheatsheet advertised
 * "Esc — Close any overlay". Several bound Escape to `window` unconditionally,
 * so one keypress closed two stacked overlays at once.
 *
 * These hooks are deliberately small and dependency-free so they can be
 * adopted incrementally, one dialog at a time, without a big-bang migration.
 */

import { useEffect, useRef } from "react";

/** Elements that can hold focus inside a dialog. */
const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Escape-to-close, arbitrated so only the TOP-most open overlay reacts.
 *
 * A module-level stack replaces the per-component `window` listeners: with
 * those, opening a column menu on top of a drawer and pressing Escape closed
 * both, because each had its own unconditional handler.
 */
const escapeStack: Array<() => void> = [];

export function useEscapeToClose(open: boolean, onClose: () => void): void {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const entry = () => onCloseRef.current();
    escapeStack.push(entry);
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Only the most recently opened overlay closes.
      if (escapeStack[escapeStack.length - 1] !== entry) return;
      e.stopPropagation();
      entry();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const i = escapeStack.lastIndexOf(entry);
      if (i >= 0) escapeStack.splice(i, 1);
    };
  }, [open]);
}

/**
 * Trap Tab inside `ref`, move focus in on open, and restore it on close.
 *
 * Without the trap, tabbing past the last control landed focus on an element
 * fully covered by the backdrop — invisible focus, which is a WCAG 2.4.11
 * failure as well as simply being lost.
 */
export function useFocusTrap(
  open: boolean,
  ref: React.RefObject<HTMLElement | null>,
): void {
  useEffect(() => {
    if (!open) return;
    const root = ref.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = () =>
      Array.from(root?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );

    // Move focus in — prefer the first control, fall back to the container.
    const first = focusables()[0];
    if (first) first.focus();
    else root?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !root) return;
      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      const active = document.activeElement;
      // Wrap at both ends, and pull focus back if it has escaped the dialog.
      if (e.shiftKey && (active === firstEl || !root.contains(active))) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && (active === lastEl || !root.contains(active))) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      // Restore focus so the keyboard user returns to where they were.
      previouslyFocused?.focus?.();
    };
  }, [open, ref]);
}

/** Lock body scroll while an overlay is open, compensating for the scrollbar
 *  so the page behind doesn't visibly shift. Reference-counted, so nested
 *  overlays don't unlock early. */
let scrollLocks = 0;
let savedOverflow = "";
let savedPaddingRight = "";

export function useScrollLock(open: boolean): void {
  useEffect(() => {
    if (!open) return;
    if (scrollLocks === 0) {
      const body = document.body;
      savedOverflow = body.style.overflow;
      savedPaddingRight = body.style.paddingRight;
      const gap = window.innerWidth - document.documentElement.clientWidth;
      body.style.overflow = "hidden";
      if (gap > 0) body.style.paddingRight = `${gap}px`;
    }
    scrollLocks += 1;
    return () => {
      scrollLocks -= 1;
      if (scrollLocks === 0) {
        document.body.style.overflow = savedOverflow;
        document.body.style.paddingRight = savedPaddingRight;
      }
    };
  }, [open]);
}

/** All three, for the common case. */
export function useDialogBehavior(
  open: boolean,
  onClose: () => void,
  ref: React.RefObject<HTMLElement | null>,
): void {
  useEscapeToClose(open, onClose);
  useFocusTrap(open, ref);
  useScrollLock(open);
}

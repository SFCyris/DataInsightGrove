/**
 * Stacking scale.
 *
 * The app had 16 ad-hoc z-index values (`z-0 … z-50`, plus arbitrary
 * `z-[5] z-[25] z-[55] z-[60] z-[70] z-[80] z-[100] z-[200]`), with `z-25`
 * and `z-[25]` both in use for the same number. The practical consequence:
 * the Mac title bar sat at `z-[55]` and painted OVER the 21 dialogs that used
 * `z-50`, and the server-status banner at `z-[60]` covered them too — while
 * its own comment claimed it sat below modals.
 *
 * One ordered scale, named by role. Numbers are spaced so a layer can be
 * slipped between two without renumbering everything.
 */
export const Z = {
  /** Canvas overlays, sticky table headers — above content, below chrome. */
  raised: 10,
  /** App chrome that content scrolls under. */
  chrome: 30,
  /** Popovers, menus, tooltips anchored to a control. */
  popover: 40,
  /** Modal dialogs and their scrim. */
  modal: 50,
  /** Toasts — above modals so a confirmation is never hidden by one. */
  toast: 60,
  /** Blocking, app-level states (auth required, server unreachable). */
  blocking: 70,
} as const;

export type ZLayer = keyof typeof Z;

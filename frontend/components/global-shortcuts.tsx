"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

/**
 * Global keyboard shortcuts that don't already have a home.
 *
 * Round-5 W5: G-chord navigation (`g h`, `g p`, `g d`, `g r`, `g c`, `g s`)
 * matches the Linear / GitHub / Notion convention so frequent users
 * can hop between top-level surfaces without touching the mouse or
 * opening the command palette. Press ``g`` then a second letter within
 * 1 second. The chord is dropped silently if the user types a
 * non-mapped second key — no noisy errors.
 *
 * Also wires ``/`` (when no input is focused) to open the command
 * palette pre-focused on its search field. Matches GitHub's search
 * shortcut.
 */
export function GlobalShortcuts() {
  const router = useRouter();

  useEffect(() => {
    let gChordArmed = false;
    let armTimer: number | null = null;

    const disarm = () => {
      gChordArmed = false;
      if (armTimer != null) {
        window.clearTimeout(armTimer);
        armTimer = null;
      }
    };

    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isInput =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if (isInput) {
        disarm();
        return;
      }
      // Ignore any chord with a modifier — those belong to other handlers.
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) {
        disarm();
        return;
      }
      if (e.repeat) return;

      // Step 1: arm the chord on ``g``.
      if (e.key === "g" && !gChordArmed) {
        gChordArmed = true;
        armTimer = window.setTimeout(disarm, 1000);
        return;
      }

      // Step 2: consume the second key if armed.
      if (gChordArmed) {
        const dest: Record<string, string> = {
          h: "/",
          p: "/pipelines",
          d: "/datasets",
          r: "/runs",
          c: "/catalog",
          s: "/settings",
        };
        const path = dest[e.key.toLowerCase()];
        disarm();
        if (path) {
          e.preventDefault();
          router.push(path);
        }
        return;
      }

      // ``/`` to focus the command palette search (open if closed).
      // Round-9 fix: previously this dispatched a synthetic ⌘K
      // unconditionally, which TOGGLED the palette closed when it was
      // already open. Skip the dispatch if any modal dialog (palette,
      // cheatsheet, tour, etc.) is currently mounted.
      if (e.key === "/") {
        const anyModalOpen = document.querySelector('[role=dialog][aria-modal=true]') !== null;
        if (anyModalOpen) return;
        e.preventDefault();
        const synth = new KeyboardEvent("keydown", {
          key: "k",
          metaKey: true,
          bubbles: true,
        });
        window.dispatchEvent(synth);
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      disarm();
    };
  }, [router]);

  // Round-5 W5: warn the user when the same pipeline is opened in two
  // tabs. The BroadcastChannel registers a soft heartbeat on every
  // pipeline-editor mount; the editor's own component listens for the
  // duplicate signal and shows a non-blocking banner. We bootstrap the
  // BroadcastChannel singleton here so the channel survives client-side
  // navigations within a single tab.
  useEffect(() => {
    if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel("dig.multi-tab.v1");
    ch.onmessage = (e) => {
      const data = e.data as { kind?: string; tabId?: string } | undefined;
      if (!data || data.kind !== "pipeline-claim") return;
      // Round-5 W5: another tab claimed the same pipeline that this
      // tab is also displaying. Each editor mount stores its own
      // tabId on window; if a foreign claim comes in for a path we're
      // also on, surface a toast.
      const myPath = window.location.pathname;
      const otherPath = (data as { path?: string }).path;
      const myTabId = (window as { __DIG_TAB_ID__?: string }).__DIG_TAB_ID__;
      if (otherPath === myPath && data.tabId !== myTabId) {
        toast.warning("Pipeline open in another tab", {
          description: "Edits there may conflict with this tab.",
          duration: 8000,
        });
      }
    };
    return () => ch.close();
  }, []);

  return null;
}

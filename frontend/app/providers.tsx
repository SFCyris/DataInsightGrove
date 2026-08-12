"use client";

import { MotionConfig } from "motion/react";
import { Toaster } from "sonner";
import { QueryProvider } from "@/lib/query";
import { useSettings, useSystemThemeWatcher } from "@/lib/settings";
import { CommandPalette } from "@/components/command-palette";
import { ShortcutsCheatsheet } from "@/components/shortcuts-cheatsheet";
import { GlobalShortcuts } from "@/components/global-shortcuts";
import { ServerStatusOverlay } from "@/components/server-status-overlay";
import { MacTitlebar } from "@/components/mac-titlebar";
import { AiKeepalive } from "@/components/ai-keepalive";

function ThemeWatcher() {
  // Make sure the store boots and the system-theme listener attaches.
  useSettings();
  useSystemThemeWatcher();
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    // `reducedMotion="user"` makes every motion/react animation in the app
    // honour the OS "reduce motion" setting — transform and layout animations
    // are skipped to their end state while opacity/colour still cross-fade.
    // Individual components were opting in inconsistently (roughly half did),
    // which left full-height drawer slides and simultaneous node spring-scales
    // running for users who had explicitly asked for less motion. This is the
    // backstop; per-component `useReducedMotion()` checks still work on top.
    <MotionConfig reducedMotion="user">
    <QueryProvider>
      <ThemeWatcher />
      {/* Mac-wrapper title-bar band — invisible in regular browsers (CSS
          hides it when html[data-dig-mac] is absent). Renders the brand
          text in the top 28pt and reserves space for the traffic lights
          so they don't overlap page content. Mounted before
          ServerStatusOverlay so the status overlay can stack visually
          below the band. */}
      <MacTitlebar />
      <ServerStatusOverlay />
      <AiKeepalive />
      {children}
      <CommandPalette />
      <ShortcutsCheatsheet />
      <GlobalShortcuts />
      <Toaster position="bottom-right" richColors closeButton />
    </QueryProvider>
    </MotionConfig>
  );
}

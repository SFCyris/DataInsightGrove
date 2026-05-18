"use client";

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
  );
}

"use client";

import { Toaster } from "sonner";
import { QueryProvider } from "@/lib/query";
import { useSettings, useSystemThemeWatcher } from "@/lib/settings";
import { CommandPalette } from "@/components/command-palette";
import { ShortcutsCheatsheet } from "@/components/shortcuts-cheatsheet";
import { ServerStatusOverlay } from "@/components/server-status-overlay";

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
      <ServerStatusOverlay />
      {children}
      <CommandPalette />
      <ShortcutsCheatsheet />
      <Toaster position="bottom-right" richColors closeButton />
    </QueryProvider>
  );
}

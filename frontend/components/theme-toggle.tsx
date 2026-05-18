"use client";

import { useSettings, setSettings, type Theme } from "@/lib/settings";

const ICONS: Record<Theme, string> = { system: "🖥️", light: "☀️", dark: "🌙" };
const LABELS: Record<Theme, string> = { system: "System", light: "Light", dark: "Dark" };
const ORDER: Theme[] = ["system", "light", "dark"];

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const settings = useSettings();
  const next = ORDER[(ORDER.indexOf(settings.theme) + 1) % ORDER.length];

  return (
    <button
      type="button"
      onClick={() => setSettings({ theme: next })}
      className="text-xs text-muted-foreground hover:text-foreground border border-border rounded-md px-2 py-1 flex items-center gap-1.5 hover:bg-muted/40 transition-colors min-h-[28px] focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
      title={`Theme: ${LABELS[settings.theme]} → click for ${LABELS[next]}`}
      aria-label={`Theme: ${LABELS[settings.theme]}. Activate to switch to ${LABELS[next]}.`}
    >
      <span aria-hidden>{ICONS[settings.theme]}</span>
      {!compact && <span>{LABELS[settings.theme]}</span>}
    </button>
  );
}

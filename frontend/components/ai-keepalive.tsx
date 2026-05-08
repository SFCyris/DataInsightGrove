"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { aiApi, api } from "@/lib/api/client";

/**
 * Tiny background pump that pings /ai/probe every N seconds to keep
 * the local LLM warm. Local engines like Ollama / llama.cpp unload
 * idle models after a timeout, which causes the next user-initiated
 * call (e.g. AI viz suggestions) to stall while the model reloads.
 *
 * Mounted once in the providers tree. Reads `ai_ping_interval_s` and
 * `ai_enabled` from the server settings. Off by default (0 = no ping).
 *
 * Implementation notes:
 *   - We piggyback on /ai/probe — it's already a tiny chat call (8
 *     output tokens, "ping" → "pong"), and it doesn't error on
 *     failure (just returns ok=false), so a network blip won't spam
 *     toasts or console errors.
 *   - setInterval, not setTimeout chain — TanStack Query handles its
 *     own cache; we want a wall-clock cadence regardless of how long
 *     the previous ping took.
 *   - When the tab is hidden (Page Visibility API) we pause the
 *     pump. There's no point keeping the model loaded for an idle
 *     background tab; the user resuming will start a new ping window.
 */
export function AiKeepalive() {
  // We tag this query as `["settings"]` so changing the interval in
  // Settings → AI Assistant invalidates the cache and we pick up the
  // new value immediately.
  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: api.listSettings,
    staleTime: 30_000,
  });

  const enabled = settingsQ.data?.find((s) => s.key === "ai_enabled")?.value === true;
  const intervalRaw = settingsQ.data?.find((s) => s.key === "ai_ping_interval_s")?.value;
  const intervalS = typeof intervalRaw === "number" ? intervalRaw : Number(intervalRaw ?? 0);

  useEffect(() => {
    if (!enabled || !Number.isFinite(intervalS) || intervalS <= 0) return;

    let cancelled = false;
    const ms = Math.max(1, intervalS) * 1000;

    const ping = () => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.hidden) return;
      // Fire-and-forget. /ai/probe always returns 200; we don't care
      // about the body. Errors only happen on network failure → noop.
      aiApi.probe().catch(() => {});
    };

    // Don't fire immediately — first ping after `ms` so opening the
    // app doesn't generate an LLM call before the user does anything.
    const id = window.setInterval(ping, ms);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [enabled, intervalS]);

  return null;
}

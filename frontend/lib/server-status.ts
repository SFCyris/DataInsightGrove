"use client";

/**
 * Server-status singleton.
 *
 * Tracks whether the backend `/health` endpoint is reachable, and exposes
 * one of four states for the overlay banner:
 *
 *   - connecting: initial page-load state, before the first ping returns.
 *                 Yellow banner — "Connecting to server…"
 *   - online:     last ping succeeded. No banner.
 *   - down:       last ping failed (timeout, network error, non-2xx).
 *                 Red banner — "Server is unreachable…"
 *   - recovered:  transient state — flips here for ~1.5 s after recovering
 *                 from `down`/`connecting`, then auto-transitions to
 *                 `online`. Green banner — "Server is online".
 *
 * Polling cadence is adaptive: 5 s when online, 1.5 s when down/connecting.
 * Short per-request timeout (3 s) so we never sit on a stuck socket.
 *
 * The same module is also exported with helpers (`markDown`, `markRecovered`)
 * so the WebSocket layer can flip state instantly on close/open instead of
 * waiting for the next health poll. That's how the overlay reacts within a
 * couple hundred ms of `dig-restart.sh` running, not the full 1.5 s.
 */

import { useSyncExternalStore } from "react";
import { API_BASE } from "@/lib/api/client";

export type ServerStatus = "connecting" | "online" | "down" | "recovered";

let _status: ServerStatus = "connecting";
const _listeners = new Set<() => void>();
let _started = false;
let _pollTimer: ReturnType<typeof setTimeout> | null = null;
let _recoverTimer: ReturnType<typeof setTimeout> | null = null;

const POLL_MS_ONLINE = 5_000;
const POLL_MS_DOWN = 1_500;
// Slow safety-net poll while the tab is hidden. We rely on visibilitychange
// for the prompt resume, but some hosts (headless preview, some background
// states) never fire that event, so we still need a backstop poll instead
// of waiting forever.
const POLL_MS_HIDDEN = 60_000;
const RECOVERED_VISIBLE_MS = 1_200;
const PING_TIMEOUT_MS = 3_000;

function notify(): void {
  for (const fn of _listeners) {
    try { fn(); } catch (e) { console.warn("server-status listener threw", e); }
  }
}

function setStatus(next: ServerStatus): void {
  if (_status === next) return;
  _status = next;
  notify();
}

function transitionAfterPing(success: boolean): void {
  if (success) {
    if (_status === "down" || _status === "connecting") {
      // Was off, now back — show "online" green flash, then auto-clear.
      setStatus("recovered");
      if (_recoverTimer) clearTimeout(_recoverTimer);
      _recoverTimer = setTimeout(() => {
        // Only auto-clear if we're still in `recovered` — if the server
        // dropped again in the meantime, leave that state alone.
        if (_status === "recovered") setStatus("online");
        _recoverTimer = null;
      }, RECOVERED_VISIBLE_MS);
    } else {
      setStatus("online");
    }
  } else {
    setStatus("down");
  }
}

async function ping(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const ac = new AbortController();
  const timeout = setTimeout(() => ac.abort(), PING_TIMEOUT_MS);
  try {
    const r = await fetch(`${API_BASE}/health`, {
      cache: "no-store",
      signal: ac.signal,
      // No auth: /health is bypassed by the bearer middleware on the backend
      // (see _AUTH_BYPASS_PATHS in dig/api/main.py).
    });
    return r.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function scheduleNext(): void {
  if (_pollTimer) clearTimeout(_pollTimer);
  const hidden = typeof document !== "undefined" && document.hidden;
  // Hidden tabs poll slowly as a safety net: visibilitychange normally
  // wakes us up promptly, but some hosts (headless preview, odd embed
  // states) don't fire it reliably, so a slow background poll keeps the
  // overlay from stalling on stale state.
  const delay = hidden
    ? POLL_MS_HIDDEN
    : _status === "online"
      ? POLL_MS_ONLINE
      : POLL_MS_DOWN;
  _pollTimer = setTimeout(loop, delay);
}

// One-shot listener that wakes the loop the moment the tab becomes visible.
// Re-attached after every hidden poll so it always points at the live state.
function attachVisibilityWake(): void {
  if (typeof document === "undefined") return;
  const onVis = () => {
    if (!document.hidden) {
      document.removeEventListener("visibilitychange", onVis);
      if (_pollTimer) clearTimeout(_pollTimer);
      loop();
    }
  };
  document.addEventListener("visibilitychange", onVis);
}

async function loop(): Promise<void> {
  // Always ping — even on a hidden tab. The cadence is what we vary, not
  // whether we check at all. (The previous behaviour of skipping the ping
  // entirely on hidden tabs left the overlay stuck on its initial
  // "connecting" state in any host where visibilitychange never fires.)
  const ok = await ping();
  transitionAfterPing(ok);
  if (typeof document !== "undefined" && document.hidden) {
    attachVisibilityWake();
  }
  scheduleNext();
}

function ensureStarted(): void {
  if (_started || typeof window === "undefined") return;
  _started = true;
  // First check is immediate so the overlay snaps to reality on page load.
  loop();
  // Cross-tab: if another tab marks the server down/up via storage events,
  // we don't currently propagate that. Each tab polls independently —
  // simpler and avoids needing a BroadcastChannel here.
}

function subscribe(cb: () => void): () => void {
  ensureStarted();
  _listeners.add(cb);
  return () => {
    _listeners.delete(cb);
  };
}

function getSnapshot(): ServerStatus {
  return _status;
}

function getServerSnapshot(): ServerStatus {
  // SSR has no live state; report neutral so the overlay doesn't flash on
  // hydration. The first client poll will correct it within ~PING_TIMEOUT_MS.
  return "online";
}

/** React hook — re-renders the consumer whenever the status flips. */
export function useServerStatus(): ServerStatus {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Force-mark the server as down. Called by the WebSocket layer when its
 *  connection closes — gives us instant feedback without waiting for the
 *  next health poll to tick. The /health poll will confirm shortly. */
export function markDown(): void {
  ensureStarted();
  if (_status !== "down") setStatus("down");
}

/** Force-mark the server as recovered. Called by the WebSocket layer's
 *  onOpen *if* we were previously down. Triggers the green flash + auto-
 *  transition to online, identical to a successful poll-after-down. */
export function markRecovered(): void {
  ensureStarted();
  transitionAfterPing(true);
}

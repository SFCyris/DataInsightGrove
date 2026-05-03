import { API_BASE, API_TOKEN } from "./client";
import { markDown, markRecovered } from "@/lib/server-status";

export type WsMessage = { topic: string; payload: Record<string, unknown> };

export function wsUrl(path: string): string {
  // API_BASE is http(s)://host:port — convert to ws(s).
  const u = new URL(path, API_BASE);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  // Browsers can't set custom headers on WS handshakes, so we pass the auth
  // token via query string. Backend BearerAuthMiddleware reads `?token=…` for
  // any /ws/* path. Empty token → no param; auth disabled deployments unaffected.
  if (API_TOKEN) {
    u.searchParams.set("token", API_TOKEN);
  }
  return u.toString();
}

/**
 * Subscribe to a backend WebSocket topic. Returns a teardown function.
 *
 * Includes exponential-backoff reconnect (1s, 2s, 4s, 8s, capped at 30s) so
 * the UI recovers automatically when the backend restarts or the user's
 * laptop wakes from sleep. The reconnect attempt also pauses while the tab
 * is hidden — no point retrying if no one is watching.
 */
export interface SubscribeOptions {
  /** Called when the WS first connects AND on every successful reconnect.
   *  The boolean argument is true on the first open, false on subsequent
   *  reconnects. Use this to invalidate stale local state — e.g. refetch
   *  the pipeline doc after the backend may have advanced its etag while
   *  the socket was down. */
  onOpen?: (isFirst: boolean) => void;
  onError?: (e: Event) => void;
}

export function subscribe(
  path: string,
  onMessage: (msg: WsMessage) => void,
  optsOrError?: SubscribeOptions | ((e: Event) => void),
): () => void {
  // Backwards-compatible: old callers passed onError as the third arg.
  const opts: SubscribeOptions = typeof optsOrError === "function"
    ? { onError: optsOrError }
    : (optsOrError ?? {});

  let ws: WebSocket | null = null;
  let closed = false;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  // The initial open is deferred by one tick — in dev React Strict Mode
  // mounts → cleans up → re-mounts every effect, which without this defer
  // would open a WebSocket and immediately .close() it mid-handshake (the
  // browser logs that as a "connection interrupted" warning). Holding the
  // timer here lets the synchronous cleanup cancel the pending open before
  // the socket is even constructed.
  let initialOpenTimer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let everOpened = false;

  const scheduleReconnect = () => {
    if (closed || reconnectTimer) return;
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (capped). Add ±20% jitter
    // so a hundred clients reconnecting after a backend restart don't
    // synchronize.
    const base = Math.min(30_000, 1000 * 2 ** attempt);
    const jittered = base * (0.8 + Math.random() * 0.4);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, jittered);
    attempt = Math.min(attempt + 1, 5);
  };

  const open = () => {
    if (closed) return;
    if (typeof document !== "undefined" && document.hidden) {
      // Defer until visible — reduces wasted reconnects on background tabs.
      const onVis = () => {
        if (!document.hidden) {
          document.removeEventListener("visibilitychange", onVis);
          open();
        }
      };
      document.addEventListener("visibilitychange", onVis);
      return;
    }

    try {
      ws = new WebSocket(wsUrl(path));
    } catch (e) {
      console.warn("ws construct failed", e);
      scheduleReconnect();
      return;
    }
    ws.onmessage = (ev) => {
      // Reset backoff on first successful message — confirms the link works.
      attempt = 0;
      try {
        onMessage(JSON.parse(ev.data));
      } catch (e) {
        console.warn("ws parse failed", e);
      }
    };
    ws.onerror = (e) => opts.onError?.(e);
    ws.onopen = () => {
      attempt = 0;  // reset backoff once connected
      pingTimer = setInterval(() => {
        try { ws?.send("ping"); } catch { /* ignore */ }
      }, 20_000);
      // Notify subscribers — they often need to invalidate stale state
      // after a reconnect (the backend may have advanced its etag while
      // the socket was down).
      try { opts.onOpen?.(!everOpened); } catch (e) { console.warn("ws onOpen callback threw", e); }
      // Tell the server-status overlay we're back. Skip on the first open
      // (just initial connect — no overlay was showing) but fire on every
      // reconnect so the green "back online" flash appears promptly,
      // ahead of the next /health poll tick.
      if (everOpened) markRecovered();
      everOpened = true;
    };
    ws.onclose = () => {
      if (pingTimer) clearInterval(pingTimer);
      pingTimer = null;
      ws = null;
      // The socket dropped — tell the server-status overlay immediately
      // instead of waiting for the next /health poll. The poll will
      // confirm; in the meantime the user sees the red banner within ms.
      if (everOpened && !closed) markDown();
      // Auto-reconnect unless the consumer asked to tear down.
      if (!closed) scheduleReconnect();
    };
  };

  initialOpenTimer = setTimeout(() => {
    initialOpenTimer = null;
    open();
  }, 0);

  return () => {
    closed = true;
    if (initialOpenTimer) clearTimeout(initialOpenTimer);
    if (pingTimer) clearInterval(pingTimer);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    initialOpenTimer = null;
    pingTimer = null;
    reconnectTimer = null;
    try { ws?.close(); } catch { /* ignore */ }
    ws = null;
  };
}

"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { API_BASE, getApiToken } from "@/lib/api/client";
import { PositiveLoader } from "@/components/positive-loader";

/**
 * Module-level memo of the most recent map viewport per (pipelineId, nodeId).
 *
 * When the user edits a param on a choropleth/heat/points step, the
 * preview re-runs and the iframe's srcDoc gets a fresh HTML string —
 * Leaflet would normally re-init + auto-fitBounds, throwing away the
 * user's pan/zoom. The rendered HTML now posts viewport changes back
 * via `postMessage`; we cache the latest here keyed by node so the
 * NEXT srcDoc swap can inject it via `window.__DIG_INITIAL_VIEW__`
 * before Leaflet's auto-fit runs.
 *
 * Module-level (not React state) on purpose: the persistence has to
 * survive component re-mounts (e.g. switching nodes and switching
 * back). Cleared automatically when the page navigates.
 */
const _mapViewports: Map<string, { lat: number; lng: number; zoom: number }> = new Map();
const _mapViewportKey = (pipelineId: string, nodeId: string) => `${pipelineId}::${nodeId}`;

/**
 * StepImagePreview — live in-place preview of a chart step (export_to_image,
 * forecast, …). Calls POST /pipelines/{id}/preview-step which renders the
 * focused Polars step on a sampled upstream and returns the artifact PNG/SVG
 * bytes; we display it inline in the editor's preview area.
 *
 * Why a component (not just an `<img src>`):
 *   1. Auth — DIG can be deployed with DIG_AUTH_TOKEN, and `<img>` doesn't
 *      send custom headers. We fetch as a blob and convert to a data URL
 *      so the same code path works locally and behind auth.
 *   2. Error state — we want to fall through to the parent's error UI when
 *      the step doesn't render (e.g. user picked an invalid column). The
 *      `<img>` element only fires onError without a status code; using
 *      useQuery + Error gives the parent the actual backend message.
 *   3. Cache busting — keying the query on `etag` means every saved param
 *      change triggers a fresh fetch; React Query handles dedup, so
 *      remounts during animation don't cause flicker.
 *
 * Why a data URL and not a blob URL: blob URLs need explicit
 * `URL.revokeObjectURL` to free memory, and that revocation interacts
 * badly with React Query's cache — when the user clicks chart A → B →
 * back to A, the cached q.data for A is still the OLD blob URL whose
 * memory we already revoked. The browser can't load a revoked blob URL,
 * so the image appears blank (only alt text renders). Data URLs
 * bypass that lifecycle entirely. The memory overhead vs blob is ~33%
 * (base64 inflation) — negligible at the chart-PNG sizes we render.
 */
interface Props {
  pipelineId: string;
  nodeId: string;
  /** Pipeline etag — bumps on every save. We key the query on it so the
   *  image refetches on the *committed* state, not on every keystroke. */
  etag: number;
  /** Optional callback fired when the render succeeds — parent can use
   *  this to swap from "data preview" to "image preview" mode. */
  onLoaded?: () => void;
  /** Optional callback fired when the render fails. Parent should hide
   *  this component and fall through to its own error UI. */
  onError?: (message: string) => void;
}

interface PreviewPayload {
  /** "image" → render in an <img>, "html" → render in an <iframe srcdoc>. */
  kind: "image" | "html";
  /** Data URL for image kinds; raw HTML string for html kind. */
  body: string;
}

export function StepImagePreview({ pipelineId, nodeId, etag, onLoaded, onError }: Props) {
  const q = useQuery<PreviewPayload, Error>({
    queryKey: ["preview-step-image", pipelineId, nodeId, etag],
    queryFn: async () => {
      // Accept both raster (image/*, image/svg+xml) and the new HTML
      // map output (text/html). The server picks the type based on the
      // step's primary artifact.
      const headers: Record<string, string> = { Accept: "image/*, text/html" };
      const _tok = getApiToken();
    if (_tok) headers["Authorization"] = `Bearer ${_tok}`;
      const url = `${API_BASE}/pipelines/${pipelineId}/preview-step?terminal=${encodeURIComponent(nodeId)}`;
      const res = await fetch(url, { method: "POST", headers });
      if (!res.ok) {
        // Try to surface the backend's actual error body (the request()
        // helper already does this for JSON endpoints; we replicate the
        // shape here since the success path returns binary).
        let detail: string | null = null;
        try {
          const j = (await res.json()) as { detail?: string };
          detail = j.detail ?? null;
        } catch {
          /* not JSON — fall back to status text */
        }
        throw new Error(detail ?? `${res.status} ${res.statusText}`);
      }
      const contentType = (res.headers.get("content-type") || "").toLowerCase();
      if (contentType.startsWith("text/html")) {
        // export_to_map returns Leaflet HTML — pass the source through
        // unchanged so we can drop it into an iframe srcdoc.
        const html = await res.text();
        return { kind: "html", body: html };
      }
      const blob = await res.blob();
      // Convert to a data URL — see component-level comment for why
      // this is preferred over URL.createObjectURL().
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error ?? new Error("read failed"));
        reader.readAsDataURL(blob);
      });
      return { kind: "image", body: dataUrl };
    },
    retry: false,
    // Don't auto-refetch on window focus — user can hit ⌘R if they want.
    refetchOnWindowFocus: false,
  });

  // Notify the parent so it can swap the preview-area UI between modes.
  // Effects (not callbacks inside queryFn) so the latest props win on remount.
  useEffect(() => {
    if (q.data) onLoaded?.();
  }, [q.data, onLoaded]);
  useEffect(() => {
    if (q.error) onError?.(q.error.message);
  }, [q.error, onError]);

  if (q.isLoading || q.isFetching) {
    return <PositiveLoader variant="computing" primary="Computing chart…" />;
  }
  if (q.error) {
    // Parent's onError handler is responsible for the visible UI; render
    // nothing here so we don't double-up.
    return null;
  }
  if (!q.data) return null;

  if (q.data.kind === "html") {
    return <MapPreviewIframe pipelineId={pipelineId} nodeId={nodeId} body={q.data.body} />;
  }

  return (
    <div className="flex flex-col items-center gap-2 max-w-full">
      {/* eslint-disable-next-line @next/next/no-img-element -- blob URL */}
      <img
        src={q.data.body}
        alt="Live chart preview"
        // Always-white background even in dark mode (matplotlib renders
        // on white). Wrap with a subtle ring + zinc-800 frame so the
        // chart doesn't punch a glaring hole in the dark editor (round-3
        // UX finding). The chart bytes themselves are matplotlib output
        // — recolouring them server-side is on the roadmap; the frame
        // softens the contrast in the meantime.
        className="max-w-full max-h-[60vh] rounded-lg border border-border dark:border-zinc-700 shadow-sm bg-white p-1 dark:bg-zinc-100 dark:ring-1 dark:ring-zinc-700/60"
      />
      <p className="text-[11px] text-muted-foreground/70">
        Live preview · sampled · ▶ Run to save the full-fidelity output
      </p>
    </div>
  );
}

/**
 * StepImageOrFallback — renders an inline chart preview for a Polars-engine
 * step if it produces one; otherwise falls through to ``fallback`` (typically
 * the parent's error / empty state).
 *
 * Centralises the "tried image, didn't render, show the error UI instead"
 * logic so callers don't have to thread useState through their JSX.
 *
 * The `fallback` prop accepts either:
 *   - a `ReactNode` (legacy) — used as-is for any failure,
 *   - or a function `(error?: Error) => ReactNode` — receives the
 *     actual `/preview-step` error so the parent can disambiguate
 *     "chart config issue" (e.g. `scatter3d needs x, y and z`) from
 *     "backend hop genuinely needed" and render an actionable hint
 *     instead of the generic "Run on backend" CTA.
 *
 * The function form is preferred for chart-step renderers — it lets
 * `humanizeSqlError` (which already pattern-matches per-chart-kind
 * errors) drive the message so the user sees what to do next, not
 * "click run".
 */
export function StepImageOrFallback({
  pipelineId,
  nodeId,
  etag,
  fallback,
}: {
  pipelineId: string;
  nodeId: string;
  etag: number;
  fallback: ReactNode | ((error?: Error) => ReactNode);
}) {
  // null = unknown (still trying), true = image rendered, false = render
  // failed (step doesn't produce one, or its execute_polars threw). The
  // key forces a fresh attempt when the user switches focused step.
  const [imgState, setImgState] = useState<null | true | false>(null);
  const [imgError, setImgError] = useState<Error | undefined>(undefined);

  // Reset state when the inputs that drive the query change. Without this
  // the previous step's image-state lingers when the user clicks to
  // another node — confusing because the spinner flashes "rendered" for
  // a frame.
  useEffect(() => {
    setImgState(null);
    setImgError(undefined);
  }, [pipelineId, nodeId, etag]);

  // While the attempt is in flight we render the StepImagePreview (which
  // shows its own spinner). Once we know the result, either keep the
  // image or replace it with the fallback (passing the error to the
  // function form so it can render a per-error message).
  if (imgState === false) {
    return (
      <>{typeof fallback === "function" ? fallback(imgError) : fallback}</>
    );
  }
  return (
    <StepImagePreview
      pipelineId={pipelineId}
      nodeId={nodeId}
      etag={etag}
      onLoaded={() => {
        setImgState(true);
        setImgError(undefined);
      }}
      onError={(message) => {
        setImgError(new Error(message));
        setImgState(false);
      }}
    />
  );
}


/**
 * MapPreviewIframe — hosts the rendered Leaflet HTML in a sandboxed
 * iframe and persists the user's pan/zoom across srcDoc swaps.
 *
 * Without this wrapper, every param edit (color scale, value column,
 * marker size, …) re-renders the HTML and Leaflet's `fitBounds` resets
 * the viewport — burying any pan/zoom the user did. The fix has two
 * halves:
 *
 *   1. The rendered HTML (server-side, in export_to_map/step.py)
 *      posts `{type: "dig:map:viewport", lat, lng, zoom}` to
 *      `window.parent` on every moveend/zoomend.
 *   2. This component listens for those messages, stashes the latest
 *      viewport in a module-level Map keyed by (pipelineId, nodeId),
 *      and on the NEXT srcDoc swap injects a tiny script setting
 *      `window.__DIG_INITIAL_VIEW__` before the rendered HTML. The
 *      Leaflet init script reads that flag and uses `map.setView`
 *      instead of `map.fitBounds` when present.
 *
 * Standalone HTML exports (no parent frame listening) silently no-op
 * — the postMessage call short-circuits when `window.parent === window`.
 */
function MapPreviewIframe({
  pipelineId,
  nodeId,
  body,
}: {
  pipelineId: string;
  nodeId: string;
  body: string;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const key = _mapViewportKey(pipelineId, nodeId);

  // Listen once per mount; the handler is keyed by (pipelineId, nodeId)
  // via the closure capture. Multiple MapPreviewIframe instances each
  // listen separately and only update their own cache entry — we don't
  // distinguish messages by source frame because the message payload
  // is identical for both surfaces and any wrong-frame write is
  // overwritten the next time the correct iframe posts.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      const data = e.data as
        | { type?: string; lat?: number; lng?: number; zoom?: number }
        | undefined;
      if (!data || data.type !== "dig:map:viewport") return;
      if (
        typeof data.lat !== "number" ||
        typeof data.lng !== "number" ||
        typeof data.zoom !== "number"
      ) return;
      // Only store from the iframe we're rendering — Window's
      // postMessage doesn't filter by frame, but contentWindow does
      // give us a reference we can compare. Falls through if the
      // iframe hasn't mounted yet.
      if (iframeRef.current && e.source && e.source !== iframeRef.current.contentWindow) {
        return;
      }
      _mapViewports.set(key, { lat: data.lat, lng: data.lng, zoom: data.zoom });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [key]);

  // Recompute the srcDoc whenever the body changes OR when we have a
  // stored viewport for this node. The injection is a tiny <script>
  // prepended to <head> so it runs BEFORE Leaflet's init script reads
  // `window.__DIG_INITIAL_VIEW__`.
  const srcDoc = useMemo(() => {
    const stored = _mapViewports.get(key);
    if (!stored) return body;
    const seed = `<script>window.__DIG_INITIAL_VIEW__ = ${JSON.stringify(stored)};</script>`;
    // Insert immediately after the opening <head> tag so it executes
    // before the rendered HTML's own scripts. Falls back to prepending
    // to the document if there's no <head> (defensive — every renderer
    // here emits one).
    const headOpen = body.search(/<head[^>]*>/i);
    if (headOpen === -1) return seed + body;
    const insertAt = body.indexOf(">", headOpen) + 1;
    return body.slice(0, insertAt) + seed + body.slice(insertAt);
  }, [body, key]);

  return (
    <div className="flex flex-col items-stretch gap-2 max-w-full w-full">
      <iframe
        ref={iframeRef}
        title="Live map preview"
        srcDoc={srcDoc}
        // sandbox="allow-scripts" only — no allow-same-origin, so the
        // iframe runs in a null origin and can't read parent state.
        // Leaflet + CDN tile fetching still work; postMessage works
        // across origin boundaries.
        sandbox="allow-scripts"
        className="w-full aspect-video min-h-[280px] max-h-[60vh] rounded-lg border border-border shadow-sm bg-white"
      />
      <p className="text-[11px] text-muted-foreground/70 text-center">
        🗺 Live map · hover a marker for the tooltip · ▶ Run to save the full HTML
      </p>
    </div>
  );
}

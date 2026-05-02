"use client";

/**
 * MacTitlebar — the thin band at the top of the window when DIG runs
 * inside its Mac wrapper (mac/DataInsightGrove.swift).
 *
 * Why this exists: the Mac wrapper uses a "full-content" window so DIG
 * can render edge-to-edge, but that means the macOS traffic-light
 * buttons (close / minimize / zoom) end up *over* the web content.
 * Instead of letting them overlap whatever the page draws there, we
 * promote the top 28pt to a designed strip — empty padding on the left
 * for the traffic lights, brand text centered, room on the right for
 * future controls.
 *
 * In a regular browser tab the strip is hidden (display: none via the
 * data-dig-mac attribute selector), and the body has zero top padding,
 * so DIG renders exactly as before.
 *
 * The component is purely visual — the *drag* behavior is handled at
 * the AppKit level by mac/DataInsightGrove.swift's NSWindow.sendEvent
 * override, which fires before any web-side event dispatch.
 */
export function MacTitlebar() {
  return (
    <div
      className={[
        // Visibility flips via globals.css rule on `html[data-dig-mac=true]`
        // — hidden in regular browsers, flex when the Swift wrapper has
        // set the data attribute.
        "dig-mac-titlebar",
        // Anchor to the very top of the viewport.
        "fixed inset-x-0 top-0 z-[55]",
        "items-center select-none",
        // Subtle separator + slight blur so the band sits cleanly above
        // any page content. Soft enough that pages with their own dark
        // backdrop (the home-page matrix tree) still look right.
        "border-b border-border/40 bg-background/70 backdrop-blur",
      ].join(" ")}
      // Block any pointer events on the band so the AppKit-level drag
      // handler in DataInsightGrove.swift sees the click first. Without
      // this, DOM elements inside the strip could capture mouse events
      // and prevent dragging. (We deliberately don't add buttons here
      // for that reason — every pixel of the band is a drag handle.)
      style={{ pointerEvents: "none" }}
      role="presentation"
      aria-hidden
    >
      {/* Reserve the leftmost 80px for the traffic-light buttons; render
          the brand text centered in the rest of the band. The text is
          intentionally muted — it provides identity without competing
          with the page's own header. */}
      <div className="w-[var(--dig-titlebar-traffic-light-w)] shrink-0" />
      <div className="flex-1 flex items-center justify-center">
        <span className="text-[11px] font-medium tracking-wider text-muted-foreground/80">
          🌳 DataInsightGrove
        </span>
      </div>
      {/* Mirror the left reserved width on the right so the brand text
          stays centered in the WINDOW, not centered in the
          post-traffic-light remainder. */}
      <div className="w-[var(--dig-titlebar-traffic-light-w)] shrink-0" />
    </div>
  );
}

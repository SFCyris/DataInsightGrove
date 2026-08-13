"use client";

/**
 * Last-resort boundary — catches throws in the root layout itself, which
 * `app/error.tsx` cannot (it sits *inside* that layout).
 *
 * This file replaces the root layout when active, so per the Next 16 docs it
 * must render its own <html> and <body>. That also means none of the app's
 * providers or CSS variables are guaranteed to be present, so the styling
 * here is deliberately inline and dependency-free rather than token-based —
 * it has to render correctly even when the thing that failed *is* the theme
 * or provider layer.
 */

export default function GlobalError({
  error,
  unstable_retry,
  reset,
}: {
  error: Error & { digest?: string };
  unstable_retry?: () => void;
  reset?: () => void;
}) {
  const retry = unstable_retry ?? reset;
  // globals.css is genuinely unavailable here (this file replaces the root
  // layout, and the prerendered _global-error.html ships no stylesheet link),
  // so the palette has to be inline. Driving it off `prefers-color-scheme`
  // keeps a dark-mode user from getting a full-screen white page — the same
  // flash the pre-paint theme script exists to prevent everywhere else. This
  // screen can't read the user's saved theme (no JS has run), so the OS
  // preference is the best available signal.
  const css = `
    :root { color-scheme: light dark; }
    .dig-ge-body { margin:0; min-height:100vh; display:flex; align-items:center;
      justify-content:center; background:#fafafa; color:#18181b;
      font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
    .dig-ge-card { max-width:420px; width:100%; padding:24px; border-radius:10px;
      border:1px solid #e4e4e7; background:#fff; text-align:center; }
    .dig-ge-msg { font-size:12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color:#52525b; background:#f4f4f5; border-radius:6px; padding:8px;
      margin:0 0 16px; text-align:left; word-break:break-word; }
    .dig-ge-sub { font-size:14px; color:#52525b; margin:0 0 16px; }
    @media (prefers-color-scheme: dark) {
      .dig-ge-body { background:#09090b; color:#fafafa; }
      .dig-ge-card { background:#18181b; border-color:#27272a; }
      .dig-ge-msg  { background:#27272a; color:#a1a1aa; }
      .dig-ge-sub  { color:#a1a1aa; }
    }
  `;
  return (
    <html lang="en">
      <body className="dig-ge-body">
        <title>Something went wrong · DataInsightGrove</title>
        <style dangerouslySetInnerHTML={{ __html: css }} />
        <div className="dig-ge-card" role="alert" aria-live="assertive">
          <div style={{ fontSize: 30, marginBottom: 8 }} aria-hidden="true">
            🌵
          </div>
          <h1 style={{ fontSize: 18, margin: "0 0 4px", fontWeight: 600 }}>
            DIG couldn&apos;t start this page
          </h1>
          <p className="dig-ge-sub">
            Your data is safe — nothing was saved or changed by this error.
          </p>
          {error.message && (
            <p className="dig-ge-msg">
              {error.message}
              {error.digest ? ` · ${error.digest}` : ""}
            </p>
          )}
          {retry && (
            <button
              onClick={() => retry()}
              style={{
                padding: "8px 14px",
                borderRadius: 8,
                border: "1px solid #10b981",
                background: "#10b981",
                color: "#022c22",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              ↻ Try again
            </button>
          )}
        </div>
      </body>
    </html>
  );
}

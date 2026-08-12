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
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
          background: "#fafafa",
          color: "#18181b",
        }}
      >
        <title>Something went wrong · DataInsightGrove</title>
        <div
          style={{
            maxWidth: 420,
            width: "100%",
            padding: 24,
            borderRadius: 10,
            border: "1px solid #e4e4e7",
            background: "#fff",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 30, marginBottom: 8 }} aria-hidden="true">
            🌵
          </div>
          <h1 style={{ fontSize: 18, margin: "0 0 4px", fontWeight: 600 }}>
            DIG couldn&apos;t start this page
          </h1>
          <p style={{ fontSize: 14, color: "#52525b", margin: "0 0 16px" }}>
            Your data is safe — nothing was saved or changed by this error.
          </p>
          {error.message && (
            <p
              style={{
                fontSize: 12,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                color: "#52525b",
                background: "#f4f4f5",
                borderRadius: 6,
                padding: 8,
                margin: "0 0 16px",
                textAlign: "left",
                wordBreak: "break-word",
              }}
            >
              {error.message}
              {error.digest ? ` · ${error.digest}` : ""}
            </p>
          )}
          <button
            onClick={() => unstable_retry()}
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
        </div>
      </body>
    </html>
  );
}

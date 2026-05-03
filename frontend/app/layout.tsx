// ─────────────────────────────────────────────────────────────────────
// Root layout for every page. This file's chief responsibility is to
// stay byte-stable between SSR and the first client render — anything
// here that produces different output on the two paths becomes a
// hydration error visible to every user.
//
// If you're adding code to this tree, follow the SSR rules:
//   - No `window` / `document` / `localStorage` / `Date.now()` /
//     `Math.random()` / locale-dependent formatting in render.
//   - Put runtime-only values behind `useState` + `useEffect`.
//   - For attributes legitimately injected by a wrapper or extension
//     after SSR (the Mac wrapper sets data-dig-mac), use
//     `suppressHydrationWarning` scoped to the specific element.
//
// Full guide: docs/UI_GUIDELINES.md → "SSR + hydration safety — the rules".
// ─────────────────────────────────────────────────────────────────────

import type { Metadata } from "next";
// Geist Sans + Geist Mono are vendored via the `geist` npm package (not
// `next/font/google`) so the actual .woff2 binaries ship with the build —
// no runtime fetch to Google's CDN, no build-time fetch either, fully
// self-contained for the OFL-licensed bundle. Attribution: Vercel + basement.studio,
// SIL Open Font License 1.1; see /licenses/Geist-OFL.txt.
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  // The literal ™ is fine in document.title — modern browsers render it cleanly.
  title: {
    default: "DataInsightGrove™ · DIG",
    template: "%s · DataInsightGrove™",
  },
  description:
    "DataInsightGrove™ (DIG™) — self-hosted, plugin-first data preparation. " +
    "The same visual pipeline runs in your browser (DuckDB-WASM) or on the " +
    "backend (DuckDB), with ML, time-series, per-row lineage, and one-click " +
    ".py / .ipynb export. AGPL-3.0; source at " +
    "https://github.com/SFCyris/DataInsightGrove.",
  applicationName: "DataInsightGrove",
  authors: [{ name: "Sebastian Cyris" }],
  keywords: [
    "DataInsightGrove", "DIG", "data preparation", "data cleansing",
    "self-hosted", "DuckDB", "Polars", "ETL", "ELT", "plugin",
  ],
  // Document the trademark + source claim in the page metadata for crawlers.
  other: {
    "trademark": "DataInsightGrove™ and DIG™ are unregistered trademarks of Sebastian Cyris. See /TRADEMARK.md.",
    "source": "https://github.com/SFCyris/DataInsightGrove",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}
      // The Mac wrapper (mac/DataInsightGrove.swift) injects
      // data-dig-mac="true" on this element via a WKUserScript that
      // fires at document-start — before React hydrates. The server
      // doesn't render that attribute, so React would normally flag
      // the mismatch. This is the canonical React escape hatch for
      // "we know this attribute is set client-side only, and the
      // intent is for the difference to exist." It's scoped to <html>
      // only — does NOT suppress warnings inside <body> or anywhere
      // deeper.
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        {/* Keyboard skip-link: first focusable element on every page,
            invisible until tabbed-to, then jumps past nav into content. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-3 focus:py-1.5 focus:rounded-md focus:bg-emerald-500 focus:text-emerald-950 focus:font-medium focus:shadow-lg"
        >
          Skip to main content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

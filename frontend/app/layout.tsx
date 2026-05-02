import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
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

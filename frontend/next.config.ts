import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide Next's dev-mode route-status badge (the small "N" pinned to the
  // bottom-left in dev). DIG already shows its own server-status overlay
  // along the top of the page, so the Next badge is redundant noise.
  // `false` only hides the badge — build/runtime errors still surface.
  // Per Next 16 docs: node_modules/next/dist/docs/01-app/03-api-reference/05-config/01-next-config-js/devIndicators.md
  devIndicators: false,

  // Allow dev-server HMR over LAN IPs (Next 16+ blocks cross-origin HMR by default).
  // DIG is meant to run on a single host but be reachable from other devices on
  // the LAN, so we accept loopback + common private ranges.
  allowedDevOrigins: [
    "127.0.0.1",
    "localhost",
    "10.0.0.0/8",
    "192.168.0.0/16",
    "172.16.0.0/12",
  ],

  async headers() {
    return [
      {
        // DuckDB-WASM bundles are pinned to the package version + content; cache
        // them aggressively so the browser doesn't re-download ~8 MB on every
        // refresh. Versioning happens via package bumps + `pnpm install` →
        // `copy-duckdb-wasm.mjs` rewriting the file content.
        source: "/duckdb-wasm/:file*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
          // Allow the wasm/worker to be loaded from the same-origin Next dev/static
          // server. The COI variant additionally needs cross-origin isolation —
          // unused today but we set the headers so it works if/when we enable it.
          { key: "Cross-Origin-Resource-Policy", value: "cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;

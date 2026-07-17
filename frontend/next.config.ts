import type { NextConfig } from "next";
import { networkInterfaces, hostname } from "node:os";

// Enumerate every non-loopback IPv4 (plus the kernel hostname) so Next 16's
// dev-origin gate accepts the LAN URLs DIG's `--global` mode advertises.
// The previous version listed CIDR ranges (`10.0.0.0/8`, …) but Next does
// NOT parse CIDR — it expects exact hostnames or `*` wildcards. Dynamic
// enumeration matches whatever interfaces the host actually has, so a
// machine on `10.0.0.80` and another on `192.168.5.42` both Just Work
// without anyone editing config.
function lanDevOrigins(): string[] {
  const out = new Set<string>(["127.0.0.1", "localhost", "[::1]"]);
  try {
    for (const ifaces of Object.values(networkInterfaces())) {
      for (const i of ifaces ?? []) {
        if (i.internal) continue;
        if (i.family === "IPv4") out.add(i.address);
      }
    }
    const hn = hostname();
    if (hn) {
      out.add(hn);
      // Some setups expose the kernel hostname as `<hn>.local` via mDNS.
      out.add(`${hn}.local`);
    }
  } catch {
    // Best-effort — if `os` lookups fail, fall through to loopback only.
  }
  // Operator override: comma-separated list, e.g.
  //   DIG_ALLOWED_DEV_ORIGINS="my-tunnel.example.com,10.0.5.42"
  const extra = process.env.DIG_ALLOWED_DEV_ORIGINS || "";
  for (const e of extra.split(",")) {
    const v = e.trim();
    if (v) out.add(v);
  }
  return Array.from(out);
}

const nextConfig: NextConfig = {
  // Hide Next's dev-mode route-status badge (the small "N" pinned to the
  // bottom-left in dev). DIG already shows its own server-status overlay
  // along the top of the page, so the Next badge is redundant noise.
  // `false` only hides the badge — build/runtime errors still surface.
  // Per Next 16 docs: node_modules/next/dist/docs/01-app/03-api-reference/05-config/01-next-config-js/devIndicators.md
  devIndicators: false,

  // Allow dev-server HMR + RSC over LAN IPs (Next 16+ blocks cross-origin
  // dev-resource access by default). See `lanDevOrigins()` above.
  allowedDevOrigins: lanDevOrigins(),

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

  // Same-origin API access — forward unmatched paths to the DIG backend so
  // the page at https://localhost:3443 can fetch /pipelines, /runs, /health,
  // etc. without triggering a second per-origin self-signed-cert prompt at
  // https://localhost:8443. Browsers track click-through trust per-origin,
  // so cross-origin fetches to an untrusted-cert host get silently dropped
  // even after the user has clicked through on the page origin.
  //
  // The TLS proxy handles HTTPS termination on port 3443 and forwards plain
  // HTTP to next dev on 3100; Next's `fallback` rewrites then forward those
  // same-origin API requests server-side (no CORS, no cert) to uvicorn on
  // 8190. WebSocket upgrades go through the same rewrite (Next 12+).
  //
  // ``fallback`` rewrites only run when the path matches neither a Next
  // page nor any file in /public — so /, /pipelines, /pipelines/<ulid>,
  // /_next/*, etc. continue to serve the React app as normal.
  // Same-origin API access via a /api/* prefix that the dev server
  // rewrites server-side to uvicorn. This decouples the page origin
  // from the API origin so:
  //
  //   - the HTTPS page at https://localhost:3443 fetches
  //     https://localhost:3443/api/pipelines — same origin, no
  //     second per-origin cert prompt
  //   - the HTTP page at http://localhost:3100 fetches
  //     http://localhost:3100/api/pipelines — no cross-origin CORS hop
  //
  // The /api/ prefix is mandatory because frontend pages and API
  // endpoints share the same name namespace (both have /pipelines).
  // Without a prefix, the fallback rewrite would either steal page
  // routes or never fire (since the page matched first).
  //
  // The capture `:path*` is interpolated into the destination so
  // `/api/pipelines/01ABC` → backend's `/pipelines/01ABC` — the prefix
  // is stripped, not forwarded. WebSocket upgrades are proxied through
  // the same rule automatically (Next 12+).
  async rewrites() {
    const target = (process.env.DIG_API_INTERNAL_URL || "http://127.0.0.1:8190").replace(/\/$/, "");
    return [
      { source: "/api/:path*", destination: `${target}/:path*` },
    ];
  },
};

export default nextConfig;

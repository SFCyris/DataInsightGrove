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
};

export default nextConfig;

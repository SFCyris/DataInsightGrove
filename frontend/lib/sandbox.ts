/**
 * Hosted-sandbox mode helpers.
 *
 * When `NEXT_PUBLIC_DIG_SANDBOX=1` is set at build time, DIG ships as a
 * read-only, browser-only experience. Backend-required steps and connectors
 * are visually gated with "🔒 needs local DIG" affordances.
 *
 * The full mock-backend client lands in a later phase. This module only
 * provides the gating primitives so feature code today can opt in cleanly.
 */

export const IS_SANDBOX =
  typeof process !== "undefined" &&
  process.env.NEXT_PUBLIC_DIG_SANDBOX === "1";

export interface SandboxableManifest {
  id: string;
  engine?: {
    primary?: string;
    browser?: "sql" | "js" | "none";
    sandbox?: "auto" | "supported" | "blocked";
  };
}

/**
 * Whether this step or connector can run in the sandbox.
 *
 * Resolution order:
 *   1. Explicit `engine.sandbox` value ("supported" | "blocked").
 *   2. Otherwise derive from `engine.browser`: "sql" | "js" → supported,
 *      "none" → blocked.
 *   3. Default → supported (be permissive; users will see runtime errors
 *      if a step actually fails).
 */
export function isSandboxSafe(m: SandboxableManifest | undefined | null): boolean {
  if (!m) return true;
  const explicit = m.engine?.sandbox;
  if (explicit === "supported") return true;
  if (explicit === "blocked") return false;
  const b = m.engine?.browser;
  if (b === "none") return false;
  return true;
}

/** "🔒 Needs local DIG" tooltip text shown on blocked steps. */
export const SANDBOX_BLOCKED_LABEL =
  "Needs local DIG — this step requires Python/Polars and isn't available in the sandbox.";

/**
 * Decode a `dig://import?pipeline=<base64-pipeline.dig.json>` URL.
 *
 * The local DIG `.app` and Linux `.desktop` register the `dig://` scheme
 * so a click in the browser sandbox or template gallery hands off to the
 * local install. This helper is shared between the sandbox build (which
 * generates the URL) and any deep-link handler.
 */
export function buildDigImportUrl(documentJson: string): string {
  // `unescape(encodeURIComponent(...))` is deprecated and slated for removal
  // in newer JS targets. Use `TextEncoder` to convert UTF-8 → bytes, then
  // base64-encode each byte as a Latin-1 char so `btoa` accepts it.
  const enc =
    typeof btoa !== "undefined" && typeof TextEncoder !== "undefined"
      ? btoa(
          Array.from(new TextEncoder().encode(documentJson))
            .map((b) => String.fromCharCode(b))
            .join(""),
        )
      : Buffer.from(documentJson, "utf-8").toString("base64");
  return `dig://import?pipeline=${enc}`;
}

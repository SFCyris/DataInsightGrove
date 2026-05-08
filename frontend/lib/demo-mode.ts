/**
 * Browser-demo build mode.
 *
 * Flag flow:
 *   NEXT_PUBLIC_DIG_DEMO=1  ⇒  isDemoMode() returns true at runtime.
 *
 * In demo mode the UI hides or disables every surface that requires a
 * persistent backend and presents the product as a stateless try-it-now
 * sandbox. The actual API stubbing (localStorage-backed datasets +
 * pipelines, no /runs, no /ai, no JDBC) is a separate phase — this module
 * is the *gate*, so feature touch-points that need to be hidden or
 * disabled have a single thing to import.
 *
 * Why a flag and not a runtime check on /health: the demo build is meant
 * to be deployable to a static host (Vercel / Cloudflare Pages) where
 * there *is no* backend. Probing /health would always fail in that
 * environment and the failure mode is noisy. A build-time flag makes the
 * demo UI predictable from page-1 paint.
 */

const _envFlag =
  // Resolved at build time; Next.js inlines NEXT_PUBLIC_* constants into
  // the bundle. We coerce common truthy strings so deployments using
  // "true" / "yes" / "on" Just Work without the operator second-guessing
  // case sensitivity.
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_DIG_DEMO ?? "").trim().toLowerCase()
    : "";

const _enabled = ["1", "true", "yes", "on"].includes(_envFlag);

/** Returns true when the build was produced with NEXT_PUBLIC_DIG_DEMO set. */
export function isDemoMode(): boolean {
  return _enabled;
}

/** Items the demo build hides or disables. Components import from here so
 *  the per-feature `if (...) return null` blocks read uniformly. Listed
 *  centrally so the eventual localStorage shim has a single checklist of
 *  "what does this build need to fake out vs. simply not show". */
export const DEMO_GATED = {
  /** AI panel + Suggest Fix + Explain — needs /ai/* endpoints. */
  ai: true,
  /** JDBC settings + connector — needs JVM + persistence. */
  jdbc: true,
  /** Pipeline runs (the ▶ Run on backend button + run history). */
  runs: true,
  /** Scheduled runs (Cron / hourly). */
  scheduledRuns: true,
  /** Webhook outbound (global webhooks settings). */
  webhooks: true,
  /** API token / auth settings — irrelevant in a stateless demo. */
  authSettings: true,
} as const;

/** True when the named feature should be hidden in this build. Always
 *  false in a non-demo build, so callers can wrap things unconditionally:
 *
 *    if (isHidden("runs")) return null;
 *    <RunButton />
 *
 *  …and the production build silently elides the check. */
export function isHidden(feature: keyof typeof DEMO_GATED): boolean {
  return _enabled && DEMO_GATED[feature];
}

/**
 * Locale-stable number + byte formatting.
 *
 * Why this exists: `Number.prototype.toLocaleString()` without an explicit
 * locale uses the JS runtime's default, which differs between server (Node,
 * usually `en-US` or whatever the OS env says) and client (the user's
 * browser). When SSR and client disagree on the grouping separator —
 * "1,234" vs "1.234" vs "1 234" — React 19's hydration validator emits
 * a "text content does not match" warning on every numeric cell.
 *
 * Pinning to "en-US" everywhere makes the output deterministic and
 * SSR-stable. If you need a different display locale, do it inside an
 * `Intl.NumberFormat` instance built in a `useEffect`, not in render.
 *
 * ────────────────────────────────────────────────────────────────────
 * RULE for anyone touching this codebase:
 *
 *   ✗ {n.toLocaleString()}                            // user's locale → SSR mismatch
 *   ✗ {n.toLocaleString(undefined, {...})}            // same trap, just explicit
 *   ✗ new Intl.NumberFormat().format(n)               // same trap (no locale arg)
 *
 *   ✓ {fmtInt(n)}                                     // en-US, integer
 *   ✓ {fmtFloat(n)}                                   // en-US, 2dp
 *   ✓ new Intl.NumberFormat("en-US").format(n)        // explicit locale
 *
 * Full rationale + the other three SSR-hydration traps are documented
 * in docs/UI_GUIDELINES.md → "SSR + hydration safety — the rules".
 * ────────────────────────────────────────────────────────────────────
 */

const LOCALE = "en-US";
const _intGrouped = new Intl.NumberFormat(LOCALE, { useGrouping: true });
const _twoDp = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Group-separated integer (e.g. 1234567 → "1,234,567"). */
export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return _intGrouped.format(Math.round(n));
}

/** Group-separated float, 2-dp. */
export function fmtFloat(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return _twoDp.format(n);
}

/** Bytes → human-readable (e.g. 1234567 → "1.2 MB"). Always en-US grouping. */
export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** Compact 4-significant-digit form for numbers shown in the grid. */
export function fmtCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return String(v);
    return Number.isInteger(v) ? fmtInt(v) : fmtFloat(v);
  }
  return String(v);
}

/**
 * Human-readable elapsed duration. Previously reimplemented in
 * three places (runs/page.tsx, runs/[id]/page.tsx, run-history.tsx)
 * with slight rounding differences. One canonical helper now.
 *
 *   - `null` / undefined → "—"
 *   - <1s   → "850ms"
 *   - <1m   → "12.34s"
 *   - <1h   → "3m 12s"
 *   - else  → "1h 23m"
 */
export function fmtDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`;
  const totalSec = Math.round(ms / 1000);
  if (ms < 3_600_000) {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}m ${s}s`;
  }
  const totalMin = Math.round(ms / 60_000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return `${h}h ${m}m`;
}

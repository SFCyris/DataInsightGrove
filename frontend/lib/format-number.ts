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

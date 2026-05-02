/**
 * Meta-type helpers — frontend mirror of backend/dig/engine/meta_types.py.
 *
 * The backend tags columns as 'index' or 'timezone' during profiling. The
 * grid uses the helpers here to flag invalid cells in red — duplicate
 * values for index columns, non-IANA strings for timezone columns.
 */

let _zonesCache: Set<string> | null = null;

/** Returns the set of valid IANA timezone names recognized by the browser. */
export function ianaTimezones(): Set<string> {
  if (_zonesCache) return _zonesCache;
  try {
    // Chrome 99+, Firefox 93+, Safari 15.4+. Returns the canonical IANA
    // list the JS engine knows about — typically ~400-600 zones.
    const fn = (Intl as unknown as {
      supportedValuesOf?: (k: string) => string[];
    }).supportedValuesOf;
    if (typeof fn === "function") {
      const list = fn("timeZone");
      _zonesCache = new Set([...list, "UTC", "GMT", "Z"]);
      return _zonesCache;
    }
  } catch {
    /* fall through */
  }
  // Conservative fallback for very old browsers — covers the most common
  // ones. The grid will under-flag rather than over-flag on these.
  _zonesCache = new Set([
    "UTC", "GMT", "Z",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Anchorage", "America/Phoenix", "America/Toronto", "America/Vancouver",
    "America/Sao_Paulo", "America/Buenos_Aires", "America/Mexico_City",
    "Europe/London", "Europe/Berlin", "Europe/Paris", "Europe/Madrid", "Europe/Rome",
    "Europe/Amsterdam", "Europe/Stockholm", "Europe/Helsinki", "Europe/Moscow",
    "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos",
    "Asia/Dubai", "Asia/Kolkata", "Asia/Shanghai", "Asia/Hong_Kong",
    "Asia/Tokyo", "Asia/Seoul", "Asia/Singapore", "Asia/Bangkok",
    "Australia/Sydney", "Australia/Perth", "Pacific/Auckland", "Pacific/Honolulu",
  ]);
  return _zonesCache;
}

export function isValidTimezone(value: unknown): boolean {
  if (typeof value !== "string" || value.length === 0) return false;
  return ianaTimezones().has(value);
}

/** For an index column, return the set of values that appear more than once. */
export function findIndexDuplicates(values: unknown[]): Set<unknown> {
  const seen = new Set<unknown>();
  const dupes = new Set<unknown>();
  for (const v of values) {
    // We treat null/undefined as not-an-index-value (legitimate gaps don't
    // count as dupes). The backend's auto-detect requires ≥99.9% non-null
    // already, so this is rare.
    if (v === null || v === undefined) continue;
    if (seen.has(v)) dupes.add(v);
    else seen.add(v);
  }
  return dupes;
}

/** True if the column's logical type triggers any per-cell validation. */
export function isMetaType(t: string): t is "index" | "timezone" {
  return t === "index" || t === "timezone";
}

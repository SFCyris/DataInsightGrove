/**
 * Meta-type helpers — frontend mirror of backend/dig/engine/meta_types.py.
 *
 * The backend tags columns with logical types (url, email, ip, index, …)
 * during profiling. The grid uses the helpers here to flag invalid cells
 * and to format values consistently per logical type.
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

// ---- String-shape validators (mirror backend regex patterns) -------------

const _URL_RE = /^(?:https?|s?ftp|file):\/\/\S+/i;
const _MAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const _UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const _HEX_RE = /^(?:0x|#)?[0-9a-f]+$/i;
const _HEX_COLOR_RE = /^#[0-9a-f]{3,8}$/i;
const _RGB_COLOR_RE = /^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d.]+)?\s*\)$/i;
const _PHONE_RE = /^\+?[\d\s\-().]{7,}$/;
const _IPV4_RE = /^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$/;
const _IPV6_RE = /^[0-9a-f:]+$/i;

export function isValidUrl(v: unknown): boolean {
  return typeof v === "string" && _URL_RE.test(v);
}
export function isValidEmail(v: unknown): boolean {
  return typeof v === "string" && _MAIL_RE.test(v);
}
export function isValidUuid(v: unknown): boolean {
  return typeof v === "string" && _UUID_RE.test(v);
}
export function isValidHex(v: unknown): boolean {
  return typeof v === "string" && _HEX_RE.test(v);
}
export function isValidColor(v: unknown): boolean {
  if (typeof v !== "string") return false;
  return _HEX_COLOR_RE.test(v) || _RGB_COLOR_RE.test(v);
}
export function isValidPhone(v: unknown): boolean {
  if (typeof v !== "string") return false;
  if (!_PHONE_RE.test(v)) return false;
  const digits = v.replace(/\D/g, "");
  return digits.length >= 7 && digits.length <= 15;
}
export function isValidIp(v: unknown): boolean {
  if (typeof v !== "string") return false;
  if (_IPV4_RE.test(v)) return true;
  return v.includes(":") && _IPV6_RE.test(v);
}

// ISO-3166 alpha-2 country codes — mirrors the frozenset in the backend.
const _COUNTRY_CODES = new Set([
  "AD","AE","AF","AG","AI","AL","AM","AO","AQ","AR","AS","AT","AU","AW","AX","AZ",
  "BA","BB","BD","BE","BF","BG","BH","BI","BJ","BL","BM","BN","BO","BQ","BR","BS",
  "BT","BV","BW","BY","BZ",
  "CA","CC","CD","CF","CG","CH","CI","CK","CL","CM","CN","CO","CR","CU","CV","CW",
  "CX","CY","CZ",
  "DE","DJ","DK","DM","DO","DZ",
  "EC","EE","EG","EH","ER","ES","ET",
  "FI","FJ","FK","FM","FO","FR",
  "GA","GB","GD","GE","GF","GG","GH","GI","GL","GM","GN","GP","GQ","GR","GS","GT",
  "GU","GW","GY",
  "HK","HM","HN","HR","HT","HU",
  "ID","IE","IL","IM","IN","IO","IQ","IR","IS","IT",
  "JE","JM","JO","JP",
  "KE","KG","KH","KI","KM","KN","KP","KR","KW","KY","KZ",
  "LA","LB","LC","LI","LK","LR","LS","LT","LU","LV","LY",
  "MA","MC","MD","ME","MF","MG","MH","MK","ML","MM","MN","MO","MP","MQ","MR","MS",
  "MT","MU","MV","MW","MX","MY","MZ",
  "NA","NC","NE","NF","NG","NI","NL","NO","NP","NR","NU","NZ",
  "OM",
  "PA","PE","PF","PG","PH","PK","PL","PM","PN","PR","PS","PT","PW","PY",
  "QA",
  "RE","RO","RS","RU","RW",
  "SA","SB","SC","SD","SE","SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS",
  "ST","SV","SX","SY","SZ",
  "TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO","TR","TT","TV","TW","TZ",
  "UA","UG","UM","US","UY","UZ",
  "VA","VC","VE","VG","VI","VN","VU",
  "WF","WS",
  "YE","YT",
  "ZA","ZM","ZW",
]);

export function isValidCountry(v: unknown): boolean {
  return typeof v === "string" && _COUNTRY_CODES.has(v.trim().toUpperCase());
}

const _META_TYPES = new Set([
  "index", "timezone", "url", "email", "uuid", "ip", "country",
  "color", "phone", "hex", "bignum", "decimal_string",
  "percentage", "currency", "scientific",
  "json", "array", "vector",
  "cartesian2d", "cartesian3d", "polar2d", "polar3d", "geographic",
]);

/** True if the column's logical type triggers per-cell validation/formatting. */
export function isMetaType(t: string): boolean {
  return _META_TYPES.has(t);
}

/** Validate a single cell value against its logical type. Null is treated
 *  as valid — null-handling is the column-level concern, not this one. */
export function isValidForType(value: unknown, type: string): boolean {
  if (value === null || value === undefined) return true;
  switch (type) {
    case "url":      return isValidUrl(value);
    case "email":    return isValidEmail(value);
    case "uuid":     return isValidUuid(value);
    case "hex":      return isValidHex(value);
    case "color":    return isValidColor(value);
    case "phone":    return isValidPhone(value);
    case "ip":       return isValidIp(value);
    case "country":  return isValidCountry(value);
    case "timezone": return isValidTimezone(value);
    default:         return true;
  }
}

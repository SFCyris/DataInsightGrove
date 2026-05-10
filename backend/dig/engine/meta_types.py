"""Meta-types: logical types layered on top of physical storage.

A meta-type adds *semantic* information to a column without changing
how DIG stores it. A `url` column is still a `string` on disk, but
DIG knows it's a URL and can:

  - render values as clickable links in the grid
  - flag malformed values in red
  - skip the "is this valid?" inference next time

This module is the **type registry**. Every meta-type DIG knows about
is a `TypeDescriptor` in the `TYPES` list below, with a detector
function that says "given this column's profile, how confidently does
my type fit?"

When a dataset is profiled, every detector runs against every column.
The top-scoring candidate becomes the column's primary type;
remaining candidates with score ≥ 0.5 are surfaced to the UI as
*alternates* so the user can see "DIG thinks this is a URL but it
could also be just a plain string" and re-cast at will.

──────────────────────────────────────────────────────────────────
Adding a new meta-type — the procedure:

  1. Append a TypeDescriptor to TYPES (id, label, base, sql_type, …)
  2. Write a detector function that returns a TypeCandidate or None.
     Detectors get the column's profile dict (name, type, min, max,
     distinctCount, nullCount, sampledRows, topValues).
  3. Add the type to backend/steps/cast_type/manifest.json's enum.
  4. Add a frontend formatter in components/grid/live-grid.tsx:fmt().
  5. Add an emoji to TYPE_EMOJI in the same file.

That's it — auto-detection, the cast dropdown, the smart-picks UX,
and the profile drawer all derive from the registry.
──────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable

# Re-exported for backwards-compat (callers used to import these directly).
INDEX_MIN_DISTINCT_FRACTION = 0.999
INDEX_MIN_NON_NULL_FRACTION = 0.999
TIMEZONE_MIN_VALID_FRACTION = 0.80
SCIENTIFIC_LOW = 1e-3
SCIENTIFIC_HIGH = 1e6


# ── Public dataclasses ────────────────────────────────────────────


@dataclass
class TypeCandidate:
    """One detected possibility for a column's logical type.

    `storage` (optional) lets a detector override the descriptor's default
    `sql_type` based on the data range. Example: a `scientific` column
    whose max |value| exceeds 1.8e308 reports storage=VARCHAR so the
    value isn't silently mauled to ±Inf when cast to DOUBLE.
    """
    type_id: str
    score: float        # 0..1 — how confident the detector is
    reason: str         # one-line, human-readable, e.g. "97% of values match URL pattern"
    storage: str | None = None  # SQL physical type override; None = use descriptor.sql_type


@dataclass
class TypeDescriptor:
    """Static metadata about a meta-type."""
    id: str             # snake_case, used as the value in cast_type.targetType
    label: str          # short display label with emoji ("📊 Percentage")
    base: str           # physical type: "string" | "integer" | "double" | …
    sql_type: str       # for cast_type's SQL emit ("DOUBLE", "VARCHAR", …)
    description: str    # one-line tooltip for the cast dropdown
    detector: Callable[[dict[str, Any]], TypeCandidate | None] = field(repr=False)


# ── IANA timezone set (cached) ────────────────────────────────────


@lru_cache(maxsize=1)
def iana_timezones() -> frozenset[str]:
    try:
        from zoneinfo import available_timezones
        zones = set(available_timezones())
    except Exception:
        zones = set()
    zones |= {"UTC", "GMT", "Z"}
    return frozenset(zones)


def is_valid_timezone(value: str | None) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return value in iana_timezones()


# ── ISO 3166 country codes (subset; cached) ───────────────────────
# Full list is ~250 entries. We hardcode the subset rather than depend
# on pycountry to keep the install lean. If you need exotic codes,
# install pycountry and swap the implementation.
#
# We accept three categories per ISO 3166-1:
#   1. **Officially assigned** alpha-2 codes (the canonical 249).
#   2. **Exceptionally reserved** (held in reserve at a country/group's
#      request, sometimes seen in real datasets in lieu of the assigned
#      code — e.g. `UK` for `GB`, `EU` for the European Union).
#   3. **Transitionally / formerly used** that have only recently been
#      reassigned and still show up in older exports (e.g. `AN` for the
#      former Netherlands Antilles, `CS` for Serbia and Montenegro,
#      `YU` for Yugoslavia, `SU` for the Soviet Union).
#
# We accept (2) and (3) silently rather than flagging them as bogus —
# a data-prep tool that scolds users for using `UK` is being pedantic.
# The validator's purpose is to catch typos, not police nomenclature.

_ISO_3166_ALPHA2 = frozenset({
    # 1. Officially assigned alpha-2 codes
    "AD","AE","AF","AG","AI","AL","AM","AO","AQ","AR","AS","AT","AU","AW","AX","AZ",
    "BA","BB","BD","BE","BF","BG","BH","BI","BJ","BL","BM","BN","BO","BQ","BR","BS","BT","BV","BW","BY","BZ",
    "CA","CC","CD","CF","CG","CH","CI","CK","CL","CM","CN","CO","CR","CU","CV","CW","CX","CY","CZ",
    "DE","DJ","DK","DM","DO","DZ",
    "EC","EE","EG","EH","ER","ES","ET",
    "FI","FJ","FK","FM","FO","FR",
    "GA","GB","GD","GE","GF","GG","GH","GI","GL","GM","GN","GP","GQ","GR","GS","GT","GU","GW","GY",
    "HK","HM","HN","HR","HT","HU",
    "ID","IE","IL","IM","IN","IO","IQ","IR","IS","IT",
    "JE","JM","JO","JP",
    "KE","KG","KH","KI","KM","KN","KP","KR","KW","KY","KZ",
    "LA","LB","LC","LI","LK","LR","LS","LT","LU","LV","LY",
    "MA","MC","MD","ME","MF","MG","MH","MK","ML","MM","MN","MO","MP","MQ","MR","MS","MT","MU","MV","MW","MX","MY","MZ",
    "NA","NC","NE","NF","NG","NI","NL","NO","NP","NR","NU","NZ",
    "OM",
    "PA","PE","PF","PG","PH","PK","PL","PM","PN","PR","PS","PT","PW","PY",
    "QA",
    "RE","RO","RS","RU","RW",
    "SA","SB","SC","SD","SE","SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS","ST","SV","SX","SY","SZ",
    "TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO","TR","TT","TV","TW","TZ",
    "UA","UG","UM","US","UY","UZ",
    "VA","VC","VE","VG","VI","VN","VU",
    "WF","WS",
    "YE","YT",
    "ZA","ZM","ZW",

    # 2. Exceptionally reserved (alpha-2 codes ISO holds in reserve, often
    # used informally even though they're not assigned country codes).
    # `UK` — United Kingdom (uses `GB`); `EU` — European Union; `EZ` —
    # Eurozone; `AC` — Ascension Island; `EA` — Ceuta & Melilla; `IC` —
    # Canary Islands; `CP` — Clipperton Island; `DG` — Diego Garcia;
    # `FX` — Metropolitan France; `TA` — Tristan da Cunha; `UN` — UN.
    "UK","EU","EZ","AC","EA","IC","CP","DG","FX","TA","UN",

    # 3. Transitionally / formerly used (recently reassigned; still in
    # archived datasets).
    # `AN` — Netherlands Antilles (split into BQ/CW/SX in 2010); `CS` —
    # Serbia & Montenegro (split RS/ME in 2006); `YU` — Yugoslavia (now
    # RS); `SU` — USSR (now RU + others); `BU` — Burma (now MM); `TP` —
    # East Timor (now TL); `ZR` — Zaire (now CD); `NT` — Saudi-Iraqi
    # Neutral Zone (dissolved 1993).
    "AN","CS","YU","SU","BU","TP","ZR","NT",
})

# Human-readable hint shown by the frontend's column-header info
# popover when the validator flags "invalid" country codes. References
# this constant via the type's `validation_help` field below so the
# explanation lives next to the data, not the UI.
_COUNTRY_VALIDATION_HELP = (
    "ISO 3166-1 alpha-2 country code (US, GB, JP, …). DIG also accepts "
    "common informal aliases — UK (formal: GB), EU, EZ — and "
    "transitionally reserved codes from older datasets (AN, CS, YU). "
    "Anything else flagged here is likely a typo or a non-standard code."
)


# ── Regex helpers ─────────────────────────────────────────────────


_DECIMAL_STRING_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_URL_RE   = re.compile(r"^https?://[^\s<>'\"]+$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
_UUID_RE  = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_IPV4_RE  = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_IPV6_RE  = re.compile(r"^[0-9a-f:]+$", re.IGNORECASE)  # loose; full IPv6 is messy
_HEX_RE   = re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE)
_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")  # E.164: + then 7-15 digits
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$", re.IGNORECASE)
_RGB_COLOR_RE = re.compile(r"^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(,\s*[\d.]+\s*)?\)$", re.IGNORECASE)
_NAMED_COLORS = frozenset({
    "black","white","red","green","blue","yellow","purple","orange","pink","cyan","magenta",
    "gray","grey","brown","navy","teal","olive","lime","aqua","silver","gold","maroon","fuchsia",
    "transparent","none",
})


def _is_decimal_string(s: str) -> bool:
    if not isinstance(s, str):
        return False
    return bool(_DECIMAL_STRING_RE.match(s.strip()))


def _is_json(s: str) -> bool:
    """JSON-shape check: starts with {/[, parses as JSON."""
    if not isinstance(s, str):
        return False
    s = s.strip()
    if not s or s[0] not in "{[":
        return False
    try:
        import json as _json
        _json.loads(s)
        return True
    except Exception:
        return False


def _is_array_string(s: str) -> bool:
    """Array-shape (string-encoded list): [a, b, c]. Stricter than JSON
    detection — only accepts top-level bracket arrays, not objects."""
    if not isinstance(s, str):
        return False
    s = s.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return False
    try:
        import json as _json
        v = _json.loads(s)
        return isinstance(v, list)
    except Exception:
        return False


def _is_numeric_array(s: str) -> bool:
    """Numeric-only array — every entry is a number. Vector candidate."""
    if not _is_array_string(s):
        return False
    try:
        import json as _json
        v = _json.loads(s)
        return all(isinstance(e, (int, float)) for e in v) and len(v) > 0
    except Exception:
        return False


def _is_url(s: str) -> bool:        return isinstance(s, str) and bool(_URL_RE.match(s))
def _is_email(s: str) -> bool:      return isinstance(s, str) and bool(_EMAIL_RE.match(s))
def _is_uuid(s: str) -> bool:       return isinstance(s, str) and bool(_UUID_RE.match(s))
def _is_ipv4(s: str) -> bool:
    if not isinstance(s, str) or not _IPV4_RE.match(s): return False
    return all(0 <= int(p) <= 255 for p in s.split("."))
def _is_ipv6(s: str) -> bool:
    if not isinstance(s, str): return False
    return ":" in s and bool(_IPV6_RE.match(s)) and 2 <= s.count(":") <= 7
def _is_ip(s: str) -> bool:         return _is_ipv4(s) or _is_ipv6(s)
def _is_hex(s: str) -> bool:        return isinstance(s, str) and bool(_HEX_RE.match(s))
def _is_phone(s: str) -> bool:      return isinstance(s, str) and bool(_PHONE_RE.match(s))
def _is_color(s: str) -> bool:
    if not isinstance(s, str): return False
    s_low = s.strip().lower()
    return (bool(_HEX_COLOR_RE.match(s_low))
            or bool(_RGB_COLOR_RE.match(s_low))
            or s_low in _NAMED_COLORS)
def _is_country(s: str) -> bool:
    if not isinstance(s, str): return False
    return s.upper() in _ISO_3166_ALPHA2


# ── Common detector helpers ───────────────────────────────────────


def _topvalues_pattern_score(top_values: list[dict], predicate: Callable[[Any], bool]) -> tuple[float, int, int]:
    """For string-pattern detectors: count-weighted fraction of top values
    matching `predicate`. Returns (score, valid_rows, total_rows).

    `total_rows` is the count of *top-K rows inspected* (not the column's
    full row count). For high-cardinality columns where every value is
    unique, the top-K covers <0.001% of the column — a 100% match on those
    K values is not a reliable signal that the rest of the column matches
    too. Callers should multiply this score by a coverage factor when the
    column's distinct count exceeds top-K (see `_coverage_penalty`).
    """
    valid_rows = 0
    total_rows = 0
    for tv in top_values or []:
        v = tv.get("value")
        n = int(tv.get("count") or 0)
        if not isinstance(v, str):
            continue
        total_rows += n
        if predicate(v):
            valid_rows += n
    if total_rows == 0:
        return (0.0, 0, 0)
    return (valid_rows / total_rows, valid_rows, total_rows)


def _coverage_penalty(profile: dict[str, Any], inspected_rows: int) -> float:
    """Multiplier in [0.5, 1.0] reflecting what fraction of non-null rows
    were actually inspected by a top-K pattern check. Caps at 0.5 even
    when coverage is near zero — a strong pattern in the top-K is *some*
    evidence, just not as much as full-column coverage.

    Why a soft floor instead of full proportional scaling: some columns
    (URLs, UUIDs) are inherently high-cardinality and the top-K is the
    best evidence available; demanding full coverage would suppress every
    such detection. The floor lets the detector fire with reduced
    confidence rather than silently miss.
    """
    sampled = profile.get("sampledRows") or 0
    nulls = profile.get("nullCount") or 0
    non_null = max(0, sampled - nulls)
    if non_null <= 0 or inspected_rows <= 0:
        return 0.5
    coverage = inspected_rows / non_null
    if coverage >= 0.95:
        return 1.0
    return max(0.5, 0.5 + 0.5 * coverage)


def _name_match(col_name: str | None, keywords: tuple[str, ...]) -> bool:
    """Cheap name-based hint. True if any keyword appears in the column name."""
    if not isinstance(col_name, str):
        return False
    low = col_name.lower()
    return any(kw in low for kw in keywords)


# ── Detectors ────────────────────────────────────────────────────


def _detect_index(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") != "integer":
        return None
    sampled = p.get("sampledRows") or 0
    distinct = p.get("distinctCount")
    nulls = p.get("nullCount") or 0
    non_null = sampled - nulls
    if not sampled or distinct is None or non_null < 2:
        return None
    if non_null / sampled < INDEX_MIN_NON_NULL_FRACTION:
        return None
    if distinct / non_null < INDEX_MIN_DISTINCT_FRACTION:
        return None
    return TypeCandidate("index", 0.95, f"{distinct}/{non_null} values are unique")


_IEEE_DOUBLE_MAX = 1.7976931348623157e308   # max finite IEEE 754 double
_IEEE_DOUBLE_MIN_NORMAL = 2.2250738585072014e-308  # smallest positive normal


def _detect_scientific(p: dict[str, Any]) -> TypeCandidate | None:
    """Detect scientific-notation candidates and pick the safest storage.

    DOUBLE works for values whose |x| is in [smallest-normal, max-finite].
    Once a column escapes that band — astronomical distances, sub-Planck
    quantities, ultra-high-precision constants — the value can't be
    represented in IEEE 754 without lossy underflow / overflow / precision
    truncation, so we promote storage to VARCHAR (lexical decimal). The
    user trades SQL pushdown for accuracy; downstream operations have to
    parse on demand, but the value is preserved.
    """
    if p.get("type") != "double":
        return None
    mn, mx = p.get("min"), p.get("max")
    try:
        abs_min = abs(float(mn)) if isinstance(mn, (int, float)) else None
        abs_max = abs(float(mx)) if isinstance(mx, (int, float)) else None
    except Exception:
        return None

    # Out-of-range for IEEE double → VARCHAR storage, value-preserving.
    if abs_max is not None and abs_max > _IEEE_DOUBLE_MAX * 0.99:
        return TypeCandidate(
            "scientific", 0.85,
            f"max |value| = {abs_max:.2e} exceeds IEEE 754 range — stored as VARCHAR",
            storage="VARCHAR",
        )
    if (abs_min is not None and 0 < abs_min < _IEEE_DOUBLE_MIN_NORMAL):
        return TypeCandidate(
            "scientific", 0.85,
            f"min |value| = {abs_min:.2e} subnormal — stored as VARCHAR",
            storage="VARCHAR",
        )

    # In-range scientific: regular DOUBLE storage with display formatting.
    if abs_max is not None and abs_max >= SCIENTIFIC_HIGH:
        return TypeCandidate("scientific", 0.85, f"max |value| = {abs_max:.2e}")
    if abs_min is not None and 0 < abs_min < SCIENTIFIC_LOW:
        return TypeCandidate("scientific", 0.85, f"min |value| = {abs_min:.2e}")
    return None


def _detect_percentage(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") != "double":
        return None
    mn, mx = p.get("min"), p.get("max")
    if not isinstance(mn, (int, float)) or not isinstance(mx, (int, float)):
        return None
    in_range = (-0.001 <= mn <= 1.001) and (-0.001 <= mx <= 1.001)
    if not in_range:
        return None
    name_hint = _name_match(p.get("name"), ("pct", "percent", "rate", "ratio", "_pc", "fraction"))
    if name_hint:
        return TypeCandidate("percentage", 0.92, f"in [0,1] and name suggests percentage")
    return TypeCandidate("percentage", 0.65, f"all values in [0,1]")


def _detect_currency(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") not in ("double", "integer"):
        return None
    if not _name_match(p.get("name"),
                       ("price", "amount", "cost", "revenue", "balance",
                        "fee", "salary", "income", "expense", "total",
                        "value", "_usd", "_eur", "_gbp")):
        return None
    return TypeCandidate("currency", 0.75, "name suggests monetary value")


def _detect_timezone(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") != "string":
        return None
    score, _, _ = _topvalues_pattern_score(p.get("topValues") or [], is_valid_timezone)
    if score >= TIMEZONE_MIN_VALID_FRACTION:
        return TypeCandidate("timezone", min(score, 0.95), f"{int(score*100)}% IANA-valid zones")
    return None


def _string_pattern_detector(type_id: str, predicate: Callable[[str], bool],
                             reason_word: str, threshold: float = 0.85, max_score: float = 0.95):
    """Factory for "is the column N% of values matching this regex?" detectors.

    Score is multiplied by `_coverage_penalty` so a 100% match on a top-K
    that covers <1% of the column produces a softer signal than a 100%
    match on a top-K that covers most of the column.
    """
    def detect(p: dict[str, Any]) -> TypeCandidate | None:
        if p.get("type") != "string":
            return None
        score, _, total = _topvalues_pattern_score(p.get("topValues") or [], predicate)
        if score >= threshold and total > 0:
            penalty = _coverage_penalty(p, total)
            adjusted = score * penalty
            reason_suffix = "" if penalty >= 1.0 else f" (top-K coverage: {int(penalty*100)}%)"
            return TypeCandidate(type_id, min(adjusted, max_score),
                                 f"{int(score*100)}% of top values are {reason_word}-shaped{reason_suffix}")
        return None
    return detect


def _detect_hex(p: dict[str, Any]) -> TypeCandidate | None:
    """Hex applies to either string ('0xCAFE') or string-encoded integers."""
    if p.get("type") not in ("string", "integer"):
        return None
    score, _, total = _topvalues_pattern_score(p.get("topValues") or [], _is_hex)
    if score >= 0.85 and total > 0:
        penalty = _coverage_penalty(p, total)
        adjusted = score * penalty
        reason_suffix = "" if penalty >= 1.0 else f" (top-K coverage: {int(penalty*100)}%)"
        return TypeCandidate("hex", min(adjusted, 0.95),
                             f"{int(score*100)}% of top values are hex-formatted{reason_suffix}")
    return None


# Storage thresholds for promoting integer-shaped columns:
#   |value| > 2^63 - 1            → HUGEINT (128-bit)
#   |value| > 2^127 - 1           → VARCHAR (lexical, arbitrary precision)
_BIGINT_MAX = 2**63 - 1
_HUGEINT_MAX = 2**127 - 1
_BIGINT_SAFETY_FACTOR = 0.9


def _detect_json(p: dict[str, Any]) -> TypeCandidate | None:
    """JSON columns: strings starting with `{` or `[` that parse cleanly.

    DuckDB has a native JSON type — much faster path-extraction than parsing
    on every row. We promote to it when a sample of values shows JSON shape.
    """
    if p.get("type") != "string":
        return None
    score, _, total = _topvalues_pattern_score(p.get("topValues") or [], _is_json)
    if score >= 0.85 and total > 0:
        return TypeCandidate(
            "json", min(score, 0.95),
            f"{int(score*100)}% of values parse as JSON",
        )
    return None


def _detect_array(p: dict[str, Any]) -> TypeCandidate | None:
    """String-encoded array columns: `[a, b, c]`. Numeric-only arrays are
    surfaced as `vector` instead — see _detect_vector below."""
    if p.get("type") != "string":
        return None
    score, _, total = _topvalues_pattern_score(p.get("topValues") or [], _is_array_string)
    if score < 0.85 or total == 0:
        return None
    # If every observed array is numeric, prefer the more specific `vector`.
    num_score, _, _ = _topvalues_pattern_score(p.get("topValues") or [], _is_numeric_array)
    if num_score >= 0.95:
        return None
    return TypeCandidate(
        "array", min(score, 0.90),
        f"{int(score*100)}% of values parse as JSON arrays",
    )


def _detect_vector(p: dict[str, Any]) -> TypeCandidate | None:
    """Vector columns: numeric-only arrays of consistent length. The
    canonical use case is ML embeddings — DuckDB's array_cosine_similarity
    et al. expect `DOUBLE[n]` (fixed-length array of doubles).

    We detect uniform-length numeric arrays and report storage=DOUBLE[n]
    where n is the observed length. Variable-length numeric arrays fall
    back to `array`.
    """
    if p.get("type") != "string":
        return None
    score, _, total = _topvalues_pattern_score(p.get("topValues") or [], _is_numeric_array)
    if score < 0.85 or total == 0:
        return None
    # Pick a representative length; if values disagree, demote to plain array.
    import json as _json
    lengths = set()
    for tv in p.get("topValues") or []:
        v = tv.get("value")
        if isinstance(v, str) and _is_numeric_array(v):
            try:
                lengths.add(len(_json.loads(v)))
            except Exception:
                pass
            if len(lengths) > 1:
                return None  # variable-length → not vector
    if len(lengths) != 1:
        return None
    n = next(iter(lengths))
    return TypeCandidate(
        "vector", min(score, 0.92),
        f"numeric arrays of fixed length {n}",
        storage=f"DOUBLE[{n}]",
    )


def _detect_decimal_string(p: dict[str, Any]) -> TypeCandidate | None:
    """Detect string columns that look like decimal numbers but exceed
    DuckDB's DECIMAL(38,n) precision — these need arbitrary-precision
    string storage so the value isn't truncated.

    Triggers on string columns where ≥85% of top values match a numeric
    shape AND at least one observed value has more than ~30 significant
    digits (DECIMAL(38,n) headroom is 38, we err conservative at 30).
    """
    if p.get("type") != "string":
        return None
    score, _, total = _topvalues_pattern_score(
        p.get("topValues") or [], _is_decimal_string,
    )
    if score < 0.85 or total == 0:
        return None
    # Look at any top value's significant-digit count.
    top = p.get("topValues") or []
    max_sig = 0
    for tv in top:
        v = tv.get("value")
        if isinstance(v, str) and _is_decimal_string(v):
            digits_only = "".join(c for c in v if c.isdigit())
            if len(digits_only) > max_sig:
                max_sig = len(digits_only)
    if max_sig <= 30:
        # DECIMAL(38, n) can hold this; skip — let `currency` / `scientific`
        # / a plain DECIMAL detector handle it.
        return None
    return TypeCandidate(
        "decimal_string", 0.85,
        f"{int(score*100)}% numeric values, max {max_sig} significant digits — arbitrary precision",
        storage="VARCHAR",
    )


def _detect_bignum(p: dict[str, Any]) -> TypeCandidate | None:
    """Promote integer columns whose magnitude exceeds BIGINT capacity.

    Storage choice is range-aware:
      - magnitude in [2^63·0.9, 2^127·0.9]  → HUGEINT (128-bit)
      - magnitude > 2^127·0.9               → VARCHAR (lexical decimal,
        arbitrary precision; downstream parsers handle large-number ops)

    Also fires on hex string columns where the decoded numeric value
    overflows BIGINT — those get parsed into HUGEINT or VARCHAR
    depending on nibble count.
    """
    t = p.get("type")
    mn, mx = p.get("min"), p.get("max")

    # Numeric integer column: check magnitude.
    if t == "integer" and isinstance(mn, (int, float)) and isinstance(mx, (int, float)):
        max_abs = max(abs(int(mn)), abs(int(mx)))
        if max_abs > _HUGEINT_MAX * _BIGINT_SAFETY_FACTOR:
            return TypeCandidate(
                "bignum", 0.90,
                f"max |value| = {max_abs:.3e} exceeds HUGEINT — stored as VARCHAR",
                storage="VARCHAR",
            )
        if max_abs >= _BIGINT_MAX * _BIGINT_SAFETY_FACTOR:
            return TypeCandidate(
                "bignum", 0.90,
                f"max |value| = {max_abs:.3e} approaches BIGINT range",
            )
        return None

    # Hex string column: nibble width drives storage choice.
    #   ≤16 nibbles  →  fits BIGINT  → stays as `hex`, not `bignum`
    #   17–32 nibbles →  fits HUGEINT → bignum, HUGEINT storage
    #   >32 nibbles  →  needs lexical → bignum, VARCHAR storage
    if t == "string":
        score, _, total = _topvalues_pattern_score(p.get("topValues") or [], _is_hex)
        if score >= 0.85 and total > 0:
            for tv in p.get("topValues") or []:
                v = tv.get("value")
                if isinstance(v, str) and _is_hex(v):
                    nibbles = len(v.lower().removeprefix("0x"))
                    if nibbles > 32:
                        return TypeCandidate(
                            "bignum", 0.85,
                            f"hex values are {nibbles} nibbles — exceeds HUGEINT, stored as VARCHAR",
                            storage="VARCHAR",
                        )
                    if nibbles > 16:
                        return TypeCandidate(
                            "bignum", 0.85,
                            f"hex values are {nibbles} nibbles wide — promoted to HUGEINT",
                        )
                    break
    return None


# ── The registry ─────────────────────────────────────────────────
#
# Order matters slightly: entries higher in the list act as tiebreakers
# when two detectors return the same score. We put more specific types
# above more general ones (e.g. uuid before hex; email before url).


TYPES: list[TypeDescriptor] = [
    # Numeric meta-types
    TypeDescriptor("index",       "🔑 Index (unique)",      "integer", "BIGINT",         "Integer column where every value should be unique. Duplicates are flagged in the grid.",
                   detector=_detect_index),
    TypeDescriptor("percentage",  "📊 Percentage",          "double",  "DECIMAL(9,6)",   "Decimal in the [0, 1] range, displayed as a percent (0.15 → 15%). Stored as DECIMAL for exact arithmetic.",
                   detector=_detect_percentage),
    TypeDescriptor("currency",    "💵 Currency",            "double",  "DECIMAL(18,4)",  "Monetary value with exact decimal arithmetic — DECIMAL(18,4) gives ±99 trillion at 4-decimal precision (covers any realistic money math without floating-point drift).",
                   detector=_detect_currency),
    TypeDescriptor("scientific",  "🔬 Scientific (IEEE)",   "double",  "DOUBLE",         "IEEE 754 double formatted in scientific notation (1.234e+10). For physics, astronomy, very small probabilities. Phase 1.2 promotes out-of-range values to VARCHAR storage.",
                   detector=_detect_scientific),
    TypeDescriptor("bignum",      "🧮 Big number",          "integer", "HUGEINT",        "128-bit signed integer (±1.7e38). Use when values exceed BIGINT range — e.g. SHA-256 fragments, genomic position counts, financial micro-units.",
                   detector=_detect_bignum),
    TypeDescriptor("decimal_string", "♾️ Decimal (string)",  "string",  "VARCHAR",        "Arbitrary-precision decimal stored as a lexical string. Use when DECIMAL(38,n) and HUGEINT both overflow — high-precision physical constants, financial micro-units, very large integers. SQL operations limited (no native SUM); value is preserved exactly.",
                   detector=_detect_decimal_string),
    TypeDescriptor("hex",         "🔢 Hex",                 "string",  "VARCHAR",        "Number written in hexadecimal notation (0xCAFE, 0xFF00FF). Numeric-decoded form lives in `bignum`.",
                   detector=_detect_hex),
    # String meta-types — most specific first
    TypeDescriptor("uuid",        "🆔 UUID",                "string",  "UUID",           "RFC 4122 universally-unique identifier. Stored as DuckDB's native 128-bit UUID type — compares + sorts faster than VARCHAR.",
                   detector=_string_pattern_detector("uuid", _is_uuid, "UUID")),
    TypeDescriptor("email",       "📧 Email",               "string",  "VARCHAR",  "Email address. Invalid entries are flagged in red.",
                   detector=_string_pattern_detector("email", _is_email, "email")),
    TypeDescriptor("url",         "🔗 URL",                 "string",  "VARCHAR",  "HTTP/HTTPS URL. Rendered as a clickable link in the grid.",
                   detector=_string_pattern_detector("url", _is_url, "URL")),
    TypeDescriptor("ip",          "🌐 IP address",          "string",  "VARCHAR",  "IPv4 or IPv6 address.",
                   detector=_string_pattern_detector("ip", _is_ip, "IP-address")),
    TypeDescriptor("phone",       "📞 Phone (E.164)",       "string",  "VARCHAR",  "Phone number in E.164 international format (+12025551234).",
                   detector=_string_pattern_detector("phone", _is_phone, "E.164 phone")),
    TypeDescriptor("country",     "🌍 Country code",        "string",  "VARCHAR",  "ISO 3166-1 alpha-2 country code (US, GB, JP, …).",
                   detector=_string_pattern_detector("country", _is_country, "ISO country code")),
    TypeDescriptor("color",       "🎨 Color",               "string",  "VARCHAR",  "CSS color: hex (#1a2b3c), rgb(), or named (red, blue, …).",
                   detector=_string_pattern_detector("color", _is_color, "CSS color")),
    TypeDescriptor("timezone",    "🌍 Timezone",            "string",  "VARCHAR",  "IANA timezone name (America/New_York, Europe/Berlin, …).",
                   detector=_detect_timezone),
    # ── Composite + structured types ───────────────────────────────────
    TypeDescriptor("json",        "📦 JSON",                "string",  "JSON",     "Semi-structured JSON object or array. DuckDB-native JSON type — supports path extraction (`->`, `->>`), array length, type-of.",
                   detector=_detect_json),
    TypeDescriptor("array",       "📚 Array",               "string",  "JSON",     "Variable-length list of values, JSON-encoded. For numeric fixed-length arrays prefer `vector`.",
                   detector=_detect_array),
    TypeDescriptor("vector",      "🧭 Vector",              "string",  "DOUBLE[]", "Fixed-length numeric array — ML embeddings, feature vectors. Storage is DuckDB's native DOUBLE[n] for fast cosine similarity / dot product / kNN.",
                   detector=_detect_vector),
    # ── Spatial coordinate types ───────────────────────────────────────
    # No automatic detection from raw data — these come from explicit casts
    # or upstream `pack_struct` steps. The convert_coordinates step does
    # lossless conversion between cartesian ↔ polar ↔ geographic.
    TypeDescriptor("cartesian2d", "📐 Cartesian (2D)",      "string",  "STRUCT(x DOUBLE, y DOUBLE)",                       "2D point (x, y). Convertible to polar2d (pure trig) or geographic via the `convert_coordinates` step.",
                   detector=lambda p: None),
    TypeDescriptor("cartesian3d", "📐 Cartesian (3D)",      "string",  "STRUCT(x DOUBLE, y DOUBLE, z DOUBLE)",             "3D point (x, y, z). Convertible to spherical polar3d.",
                   detector=lambda p: None),
    TypeDescriptor("polar2d",     "🧭 Polar (2D)",          "string",  "STRUCT(r DOUBLE, theta DOUBLE)",                   "Polar coordinate (r, θ) — radius + angle in radians. Convertible to cartesian2d (lossless).",
                   detector=lambda p: None),
    TypeDescriptor("polar3d",     "🧭 Polar (3D)",          "string",  "STRUCT(r DOUBLE, theta DOUBLE, phi DOUBLE)",       "Spherical polar (r, θ, φ). Convertible to cartesian3d.",
                   detector=lambda p: None),
    TypeDescriptor("geographic",  "🌍 Geographic",          "string",  "GEOMETRY",                                         "Point on Earth — lat/lon stored as DuckDB-spatial GEOMETRY (WKB). Distance is great-circle (Haversine). Convertible to cartesian (ECEF) via the `convert_coordinates` step.",
                   detector=lambda p: None),
]


def descriptor(type_id: str) -> TypeDescriptor | None:
    for t in TYPES:
        if t.id == type_id:
            return t
    return None


# ── Top-level detection entry point ──────────────────────────────


# Threshold for surfacing as an "alternate" candidate in the UI. Below
# this we consider the match too weak to bother the user with.
ALTERNATE_MIN_SCORE = 0.50


def detect_candidates(col_profile: dict[str, Any]) -> list[TypeCandidate]:
    """Run every detector against a column's profile, return ranked list.

    The first item is the highest-scoring candidate (DIG's pick). Any
    additional items with score ≥ ALTERNATE_MIN_SCORE are surfaced as
    alternates in the UI so the user can re-cast easily.
    """
    out: list[TypeCandidate] = []
    for t in TYPES:
        try:
            cand = t.detector(col_profile)
        except Exception:
            cand = None
        if cand is not None:
            out.append(cand)
    out.sort(key=lambda c: c.score, reverse=True)
    return out


# ── Backwards-compat shims ───────────────────────────────────────
# Earlier callers imported these directly. Keep them working.


def detect_index(*, distinct: int | None, non_null: int | None,
                 sampled: int | None) -> bool:
    """Legacy wrapper — prefer detect_candidates() on the col profile."""
    if not sampled or distinct is None or non_null is None or non_null < 2:
        return False
    return (
        non_null / sampled >= INDEX_MIN_NON_NULL_FRACTION
        and distinct / non_null >= INDEX_MIN_DISTINCT_FRACTION
    )


def detect_scientific(*, abs_min: float | None, abs_max: float | None) -> bool:
    if abs_max is not None and abs_max >= SCIENTIFIC_HIGH:
        return True
    if abs_min is not None and 0 < abs_min < SCIENTIFIC_LOW:
        return True
    return False


def detect_timezone_from_top(top_values: list[dict]) -> bool:
    score, _, _ = _topvalues_pattern_score(top_values, is_valid_timezone)
    return score >= TIMEZONE_MIN_VALID_FRACTION
